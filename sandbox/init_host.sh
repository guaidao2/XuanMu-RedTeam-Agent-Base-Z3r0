#!/bin/bash

set -eu

is_ipv4() {
  local ip="$1"
  local octet
  local -a octets

  [[ "$ip" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]] || return 1

  IFS=. read -r -a octets <<< "$ip"
  for octet in "${octets[@]}"; do
    ((10#$octet >= 0 && 10#$octet <= 255)) || return 1
  done
}

read -r -p "Docker host IP [127.0.0.1]: " HOST_IP
HOST_IP="${HOST_IP:-127.0.0.1}"

if ! is_ipv4 "$HOST_IP"; then
  echo "Invalid Docker host IP: $HOST_IP" >&2
  exit 1
fi

SERVER_SAN="IP:${HOST_IP}"
if [[ "$HOST_IP" != "127.0.0.1" ]]; then
  SERVER_SAN="${SERVER_SAN},IP:127.0.0.1"
fi

CERT_DIR="/etc/docker/certs.d"
WORK_DIR="$(mktemp -d)"
CLIENT_CA="docker-client-ca.pem"
CLIENT_CERT="docker-client-cert.pem"
CLIENT_KEY="docker-client-key.pem"
CLIENT_CA_TMP="${CLIENT_CA}.tmp.$$"
CLIENT_CERT_TMP="${CLIENT_CERT}.tmp.$$"
CLIENT_KEY_TMP="${CLIENT_KEY}.tmp.$$"

cleanup() {
  rm -rf "$WORK_DIR"
  rm -f "$CLIENT_CA_TMP" "$CLIENT_CERT_TMP" "$CLIENT_KEY_TMP"
}

validate_output_paths() {
  local file

  for file in "$CLIENT_CA" "$CLIENT_CERT" "$CLIENT_KEY"; do
    if [[ -e "$file" && ! -f "$file" ]]; then
      echo "Output path is not a regular file: $file" >&2
      exit 1
    fi
  done
}

validate_generated_files() {
  local file
  local ca_text
  local server_text
  local client_text

  for file in \
    "$WORK_DIR/docker-ca.crt" \
    "$WORK_DIR/docker-server.crt" \
    "$WORK_DIR/docker-server.key" \
    "$WORK_DIR/docker-client-cert.pem" \
    "$WORK_DIR/docker-client-key.pem"; do
    if [[ ! -s "$file" ]]; then
      echo "Generated file is missing or empty: $file" >&2
      exit 1
    fi
  done

  openssl x509 -in "$WORK_DIR/docker-ca.crt" -noout >/dev/null
  openssl x509 -in "$WORK_DIR/docker-server.crt" -noout >/dev/null
  openssl x509 -in "$WORK_DIR/docker-client-cert.pem" -noout >/dev/null
  openssl pkey -in "$WORK_DIR/docker-server.key" -noout >/dev/null
  openssl pkey -in "$WORK_DIR/docker-client-key.pem" -noout >/dev/null
  openssl verify -purpose sslserver -CAfile "$WORK_DIR/docker-ca.crt" "$WORK_DIR/docker-server.crt" >/dev/null
  openssl verify -purpose sslclient -CAfile "$WORK_DIR/docker-ca.crt" "$WORK_DIR/docker-client-cert.pem" >/dev/null

  ca_text="$(openssl x509 -in "$WORK_DIR/docker-ca.crt" -noout -text)"
  server_text="$(openssl x509 -in "$WORK_DIR/docker-server.crt" -noout -text)"
  client_text="$(openssl x509 -in "$WORK_DIR/docker-client-cert.pem" -noout -text)"

  grep -q "CA:TRUE" <<< "$ca_text"
  grep -q "Certificate Sign" <<< "$ca_text"
  grep -q "CRL Sign" <<< "$ca_text"
  grep -q "TLS Web Server Authentication" <<< "$server_text"
  grep -q "TLS Web Client Authentication" <<< "$client_text"
}

trap cleanup EXIT

validate_output_paths

mkdir -p "$CERT_DIR"

openssl genrsa -out "$WORK_DIR/docker-ca.key" 4096

cat > "$WORK_DIR/docker-ca.cnf" <<EOF
[req]
distinguished_name = dn
x509_extensions = v3_ca
prompt = no

[dn]
CN = Sandbox Host Private CA

[v3_ca]
basicConstraints = critical,CA:TRUE
keyUsage = critical,keyCertSign,cRLSign
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid:always,issuer
EOF

openssl req -x509 -new -nodes \
  -key "$WORK_DIR/docker-ca.key" \
  -sha256 \
  -days 3650 \
  -out "$WORK_DIR/docker-ca.crt" \
  -extensions v3_ca \
  -config "$WORK_DIR/docker-ca.cnf" \
  -subj "/CN=Sandbox Host Private CA"

openssl genrsa -out "$WORK_DIR/docker-server.key" 2048

openssl req -new \
  -key "$WORK_DIR/docker-server.key" \
  -out "$WORK_DIR/docker-server.csr" \
  -subj "/CN=${HOST_IP}"

cat > "$WORK_DIR/docker-server.ext" <<EOF
basicConstraints = critical,CA:FALSE
keyUsage = critical,digitalSignature,keyEncipherment
subjectAltName = ${SERVER_SAN}
extendedKeyUsage = serverAuth
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid,issuer
EOF

openssl x509 -req \
  -in "$WORK_DIR/docker-server.csr" \
  -CA "$WORK_DIR/docker-ca.crt" \
  -CAkey "$WORK_DIR/docker-ca.key" \
  -CAcreateserial \
  -out "$WORK_DIR/docker-server.crt" \
  -extfile "$WORK_DIR/docker-server.ext" \
  -days 365 \
  -sha256

openssl genrsa -out "$WORK_DIR/docker-client-key.pem" 2048

openssl req -new \
  -key "$WORK_DIR/docker-client-key.pem" \
  -out "$WORK_DIR/docker-client.csr" \
  -subj "/CN=sandbox-client"

cat > "$WORK_DIR/docker-client.ext" <<EOF
basicConstraints = critical,CA:FALSE
keyUsage = critical,digitalSignature,keyEncipherment
extendedKeyUsage = clientAuth
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid,issuer
EOF

openssl x509 -req \
  -in "$WORK_DIR/docker-client.csr" \
  -CA "$WORK_DIR/docker-ca.crt" \
  -CAkey "$WORK_DIR/docker-ca.key" \
  -CAcreateserial \
  -out "$WORK_DIR/docker-client-cert.pem" \
  -extfile "$WORK_DIR/docker-client.ext" \
  -days 365 \
  -sha256

validate_generated_files

cat > "$WORK_DIR/daemon.json" <<EOF
{
  "hosts": [
    "tcp://0.0.0.0:2376",
    "unix:///var/run/docker.sock"
  ],
  "tlsverify": true,
  "tlscacert": "$CERT_DIR/docker-server-ca.crt",
  "tlscert": "$CERT_DIR/docker-server.crt",
  "tlskey": "$CERT_DIR/docker-server.key"
}
EOF

install -m 644 "$WORK_DIR/docker-ca.crt" "$CERT_DIR/docker-server-ca.crt"
install -m 644 "$WORK_DIR/docker-server.crt" "$CERT_DIR/docker-server.crt"
install -m 600 "$WORK_DIR/docker-server.key" "$CERT_DIR/docker-server.key"
install -m 644 "$WORK_DIR/daemon.json" /etc/docker/daemon.json

install -m 644 "$WORK_DIR/docker-ca.crt" "$CLIENT_CA_TMP"
install -m 644 "$WORK_DIR/docker-client-cert.pem" "$CLIENT_CERT_TMP"
install -m 600 "$WORK_DIR/docker-client-key.pem" "$CLIENT_KEY_TMP"
mv -f "$CLIENT_CA_TMP" "$CLIENT_CA"
mv -f "$CLIENT_CERT_TMP" "$CLIENT_CERT"
mv -f "$CLIENT_KEY_TMP" "$CLIENT_KEY"

echo "Docker TLS certificates generated successfully"
echo "Restart Docker for /etc/docker/daemon.json to take effect"
echo "Client files written to current directory: $CLIENT_CA, $CLIENT_CERT, $CLIENT_KEY"
echo "Client usage: docker --tlsverify --tlscacert=$CLIENT_CA --tlscert=$CLIENT_CERT --tlskey=$CLIENT_KEY -H=tcp://${HOST_IP}:2376 version"
