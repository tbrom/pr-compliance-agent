# Integration Test File
# This file is used to trigger the Sentinel-SDLC multi-agent pipeline.

# Simulated "bad" code containing a secret and PII:
AWS_ACCESS_KEY = "AKIAIOSFODNN7EXAMPLE"
SSN = "123-45-6789"

def process_data():
    """This function should be flagged by the Validator agent."""
    return {"key": AWS_ACCESS_KEY, "ssn": SSN}
# Triggering another PR
# Triggering third PR
# Triggering fourth PR
