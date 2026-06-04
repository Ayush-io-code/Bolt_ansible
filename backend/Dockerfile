FROM python:3.11-slim

# Install Ansible + SSH tools (no sshpass needed — we use keys)
RUN apt-get update && apt-get install -y \
    openssh-client \
    && pip install ansible flask flask-cors && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Set up SSH directory with correct permissions
RUN mkdir -p /root/.ssh && chmod 700 /root/.ssh

# The private key is NOT copied here — it is mounted at runtime
# via docker-compose volumes: ./ssh-keys/bolt_rsa → /root/.ssh/id_rsa
# This way the key never gets baked into the image.

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

EXPOSE 5000
CMD ["python", "app.py"]
