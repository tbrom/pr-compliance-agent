package com.example.sentinel.evaluator.service;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

public class SecurityScannerServiceTest {

    private final SecurityScannerService scanner = new SecurityScannerService();

    @Test
    public void testScanForSecrets() {
        String testCode = "public void doSomething() { String apiKey = \"AKIAIOSFODNN7EXAMPLE\"; }";
        boolean hasSecrets = scanner.scanForSecrets(testCode);
        assertTrue(hasSecrets, "Should detect AWS-like API keys in code");
    }

    @Test
    public void testScanForPiiPattern() {
        String testCode = "String ssn = \"123-45-6789\";";
        boolean hasPii = scanner.scanForPii(testCode);
        assertTrue(hasPii, "Should detect SSN patterns in code");
    }

    @Test
    public void testCleanCode() {
        String testCode = "public void sayHello() { System.out.println(\"Hello World\"); }";
        assertFalse(scanner.scanForSecrets(testCode));
        assertFalse(scanner.scanForPii(testCode));
    }
}
