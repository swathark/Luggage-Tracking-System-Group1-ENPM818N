# Dynamically generate private keys for the application Load Balancer
resource "tls_private_key" "self_signed" {
  algorithm = "RSA"
  rsa_bits  = 2048
}

# Produce the Self-Signed cert mimicking production CA models safely (Zero extra cost!)
resource "tls_self_signed_cert" "alb_cert" {
  private_key_pem = tls_private_key.self_signed.private_key_pem

  subject {
    common_name  = "cargo-portal.internal.local"
    organization = "Global Luggage Logistics Demo"
  }

  validity_period_hours = 8760 # 1 Year

  allowed_uses = [
    "key_encipherment",
    "digital_signature",
    "server_auth",
  ]
}

# Automatically upload certs into AWS Certificate Manager
resource "aws_acm_certificate" "alb_cert" {
  private_key      = tls_private_key.self_signed.private_key_pem
  certificate_body = tls_self_signed_cert.alb_cert.cert_pem

  tags = {
    Name = "luggage-alb-cert"
  }
}
