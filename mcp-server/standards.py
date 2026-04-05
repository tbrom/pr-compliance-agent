def get_security_standard(standard_name: str) -> str:
    standards = {
        "PCI-DSS": "PCI-DSS Requirement 3: Protect stored cardholder data. Requires strong encryption and key management.",
        "SOC2": "SOC2 CC7.1: To meet its objectives, the entity uses detection and monitoring procedures to identify (1) changes to configurations that result in the introduction of new vulnerabilities, and (2) susceptibilities to newly discovered vulnerabilities. Proper audit logging and retention is required.",
        "OWASP": "OWASP Top 10 A01:2021 - Broken Access Control. Ensure users cannot act outside of their intended permissions.",
        "DATA_FABRIC": "Enterprise Data Fabric Standard 1.0: All PII must pass through the enterprise Tokenization service. Direct database storage of raw SSNs or account numbers is strictly prohibited.",
    }
    
    return standards.get(standard_name.upper(), f"Standard '{standard_name}' not found. Available standards: {', '.join(standards.keys())}")
