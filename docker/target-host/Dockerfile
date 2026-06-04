FROM ubuntu:22.04

RUN apt-get update && apt-get install -y \
    openssh-server \
    python3 \
    sudo \
    && rm -rf /var/lib/apt/lists/*

# Create ansible user with sudo (no password needed for sudo)
RUN useradd -m -s /bin/bash ansible && \
    usermod -aG sudo ansible && \
    echo "ansible ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers

# Set up root SSH directory
RUN mkdir -p /root/.ssh && chmod 700 /root/.ssh && mkdir -p /run/sshd

# Copy the public key into authorized_keys so Ansible can SSH in using the private key
# The public key must exist at ./ssh-keys/bolt_rsa.pub before building
COPY ssh-keys/bolt_rsa.pub /root/.ssh/authorized_keys
RUN chmod 600 /root/.ssh/authorized_keys

# SSH hardening: disable password auth, allow only key-based login
RUN sed -i 's/#PermitRootLogin prohibit-password/PermitRootLogin yes/'   /etc/ssh/sshd_config && \
    sed -i 's/#PasswordAuthentication yes/PasswordAuthentication no/'     /etc/ssh/sshd_config && \
    sed -i 's/PasswordAuthentication yes/PasswordAuthentication no/'      /etc/ssh/sshd_config && \
    echo "PubkeyAuthentication yes" >> /etc/ssh/sshd_config

EXPOSE 22
CMD ["/usr/sbin/sshd", "-D"]
