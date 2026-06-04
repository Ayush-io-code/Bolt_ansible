"""
Bolt Backend
-----------------
REST API that manages playbooks, hosts, and job execution.
"""

import os, subprocess, uuid, json, yaml, threading
from datetime import datetime
from flask import Flask, jsonify, request
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

ANSIBLE_BASE   = os.environ.get("ANSIBLE_BASE", "/ansible")
PLAYBOOKS_DIR  = f"{ANSIBLE_BASE}/playbooks"
INVENTORY_FILE = f"{ANSIBLE_BASE}/inventory/hosts.yml"
LOGS_DIR       = f"{ANSIBLE_BASE}/logs"

os.makedirs(LOGS_DIR, exist_ok=True)

# ── In-memory job store ────────────────────────────────────────────────────────
jobs = {}


# ── Helpers ───────────────────────────────────────────────────────────────────

def load_inventory():
    if not os.path.exists(INVENTORY_FILE):
        return {}
    with open(INVENTORY_FILE) as f:
        return yaml.safe_load(f) or {}

def save_inventory(data):
    with open(INVENTORY_FILE, "w") as f:
        yaml.dump(data, f, default_flow_style=False)

def get_all_hosts(inventory):
    hosts = []
    for group, content in inventory.items():
        if group == "all":
            continue
        if isinstance(content, dict) and "hosts" in content:
            for hostname, vars_ in (content["hosts"] or {}).items():
                hosts.append({"name": hostname, "group": group, "vars": vars_ or {}})
    return hosts

def load_playbook_meta(playbook_name):
    meta_path = f"{PLAYBOOKS_DIR}/{playbook_name}.meta.json"
    if os.path.exists(meta_path):
        with open(meta_path) as f:
            return json.load(f)
    return {"description": "", "inputs": []}

def run_playbook_thread(job_id, playbook, hosts, extra_vars, distro):
    """Run ansible-playbook in a background thread and stream output to log file."""
    log_path = f"{LOGS_DIR}/{job_id}.log"
    jobs[job_id]["status"] = "running"
    jobs[job_id]["started_at"] = datetime.utcnow().isoformat()

    # Inject distro hint as extra var so playbooks can use it
    if distro:
        extra_vars["target_distro"] = distro

    ev_str = json.dumps(extra_vars)
    host_pattern = ",".join(hosts) if hosts else "all"

    cmd = [
        "ansible-playbook",
        f"{PLAYBOOKS_DIR}/{playbook}.yml",
        "-i", INVENTORY_FILE,
        "--limit", host_pattern,
        "--extra-vars", ev_str,
        "-v"
    ]

    with open(log_path, "w") as log_file:
        log_file.write(f"=== Bolt Job {job_id} ===\n")
        log_file.write(f"Playbook : {playbook}\n")
        log_file.write(f"Hosts    : {host_pattern}\n")
        log_file.write(f"Distro   : {distro or 'auto-detect'}\n")
        log_file.write(f"Vars     : {ev_str}\n")
        log_file.write(f"Started  : {jobs[job_id]['started_at']}\n")
        log_file.write("=" * 50 + "\n\n")
        log_file.flush()

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )
        for line in proc.stdout:
            log_file.write(line)
            log_file.flush()

        proc.wait()

    jobs[job_id]["status"] = "success" if proc.returncode == 0 else "failed"
    jobs[job_id]["return_code"] = proc.returncode
    jobs[job_id]["finished_at"] = datetime.utcnow().isoformat()


# ── Routes: Playbooks ──────────────────────────────────────────────────────────

@app.route("/api/playbooks", methods=["GET"])
def list_playbooks():
    if not os.path.exists(PLAYBOOKS_DIR):
        return jsonify([])
    playbooks = []
    for f in sorted(os.listdir(PLAYBOOKS_DIR)):
        if f.endswith(".yml"):
            name = f[:-4]
            meta = load_playbook_meta(name)
            playbooks.append({"name": name, **meta})
    return jsonify(playbooks)

@app.route("/api/playbooks/<name>", methods=["GET"])
def get_playbook(name):
    meta = load_playbook_meta(name)
    return jsonify({"name": name, **meta})


# ── Routes: Hosts / Inventory ──────────────────────────────────────────────────

@app.route("/api/hosts", methods=["GET"])
def list_hosts():
    inventory = load_inventory()
    return jsonify(get_all_hosts(inventory))

@app.route("/api/hosts", methods=["POST"])
def add_host():
    body = request.json
    name  = body.get("name", "").strip()
    group = body.get("group", "ungrouped").strip()
    ansible_host = body.get("ansible_host", name).strip()

    if not name:
        return jsonify({"error": "name is required"}), 400

    inventory = load_inventory()
    if group not in inventory:
        inventory[group] = {"hosts": {}}
    if inventory[group].get("hosts") is None:
        inventory[group]["hosts"] = {}

    host_vars = {
        "ansible_host": ansible_host,
        "ansible_user": body.get("ansible_user", "root"),
        "ansible_ssh_common_args": "-o StrictHostKeyChecking=no"
    }
    ssh_pass = body.get("ansible_ssh_pass", "")
    if ssh_pass:
        host_vars["ansible_ssh_pass"] = ssh_pass
        host_vars["ansible_become_pass"] = ssh_pass  # fix multipassword prompt
    ssh_key = body.get("ansible_ssh_private_key_file", "")
    if ssh_key:
        host_vars["ansible_ssh_private_key_file"] = ssh_key

    inventory[group]["hosts"][name] = host_vars
    save_inventory(inventory)
    return jsonify({"ok": True, "host": name})

@app.route("/api/hosts/<name>", methods=["DELETE"])
def delete_host(name):
    inventory = load_inventory()
    for group in inventory.values():
        if isinstance(group, dict) and "hosts" in group:
            if name in (group["hosts"] or {}):
                del group["hosts"][name]
                save_inventory(inventory)
                return jsonify({"ok": True})
    return jsonify({"error": "host not found"}), 404


# ── Routes: Jobs ───────────────────────────────────────────────────────────────

@app.route("/api/jobs", methods=["POST"])
def create_job():
    body = request.json
    playbook   = body.get("playbook")
    hosts      = body.get("hosts", [])
    extra_vars = body.get("extra_vars", {})
    distro     = body.get("distro", "")   # e.g. "ubuntu", "centos", "rhel"

    if not playbook:
        return jsonify({"error": "playbook is required"}), 400

    job_id = str(uuid.uuid4())[:8]
    jobs[job_id] = {
        "id":          job_id,
        "playbook":    playbook,
        "hosts":       hosts,
        "distro":      distro,
        "extra_vars":  extra_vars,
        "status":      "queued",
        "created_at":  datetime.utcnow().isoformat(),
        "started_at":  None,
        "finished_at": None,
    }

    t = threading.Thread(target=run_playbook_thread,
                         args=(job_id, playbook, hosts, extra_vars, distro))
    t.daemon = True
    t.start()

    return jsonify(jobs[job_id]), 201

@app.route("/api/jobs", methods=["GET"])
def list_jobs():
    return jsonify(sorted(jobs.values(), key=lambda j: j["created_at"], reverse=True))

@app.route("/api/jobs/<job_id>", methods=["GET"])
def get_job(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "not found"}), 404
    return jsonify(job)

@app.route("/api/jobs/<job_id>/log", methods=["GET"])
def get_job_log(job_id):
    log_path = f"{LOGS_DIR}/{job_id}.log"
    if not os.path.exists(log_path):
        return "Log not available yet.", 200, {"Content-Type": "text/plain"}
    with open(log_path) as f:
        return f.read(), 200, {"Content-Type": "text/plain"}


# ── Health check ───────────────────────────────────────────────────────────────

@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "bolt-backend"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
