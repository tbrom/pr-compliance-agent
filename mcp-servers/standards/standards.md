# Sentinel-SDLC Enterprise Compliance Standards

## 🔓 SEC-001: PII Protection
Enterprise Data Fabric Standard 1.0: All PII must pass through the enterprise Tokenization service. 
Direct database storage of raw SSNs, account numbers, or credit card information is strictly prohibited. 
Look for patterns of 9-digit numbers or field names like `ssn`, `tax_id`, or `card_num`.

## 🗝️ SEC-002: Secret Management
Cloud Security Standard: Hardcoding of API keys, client secrets, or private keys in the source code is forbidden. 
All secrets must be retrieved from the Enterprise Secret Manager at runtime. 
Check for assignments to variables like `AWS_KEY`, `CLIENT_SECRET`, or `API_KEY`.

## 📦 SEC-003: Container Security
Container Governance: All Dockerfiles must use hardened base images. 
Official Alpine or Wolfram images are preferred over general-purpose distributions like Ubuntu or Debian. 
Verify the `FROM` instruction in any Dockerfile.

## 🌉 SEC-004: Network Communication
Infrastructure Policy: Internal service-to-service communication must use Mutual TLS (mTLS). 
Verify that service configurations (Istio/Linkerd) are correctly set for STRICT mtls mode.
Avoid `http://` calls inside service definitions; use `https://` with internal PKI.
