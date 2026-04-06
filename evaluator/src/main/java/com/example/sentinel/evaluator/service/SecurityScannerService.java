package com.example.sentinel.evaluator.service;

import org.springframework.stereotype.Service;
import org.springframework.beans.factory.annotation.Autowired;
import java.util.regex.Pattern;
import java.util.regex.Matcher;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

@Service
public class SecurityScannerService {

    private static final Logger logger = LoggerFactory.getLogger(SecurityScannerService.class);

    private static final Pattern AWS_KEY_PATTERN = Pattern.compile("AKIA[0-9A-Z]{16}");
    private static final Pattern SSN_PATTERN = Pattern.compile("\\d{3}-\\d{2}-\\d{4}");

    @Autowired
    private SecurityAIService aiService;

    public boolean scanForSecrets(String code) {
        if (code == null) return false;
        
        // Tier 1: Fast Regex
        Matcher matcher = AWS_KEY_PATTERN.matcher(code);
        if (matcher.find()) return true;

        // Tier 2: AI Reasoning
        String aiResult = aiService.scan(code);
        logger.info("AI Scan Result: {}", aiResult);
        return !aiResult.contains("COMPLIANT");
    }

    public boolean scanForPii(String code) {
        if (code == null) return false;
        
        // Tier 1: Fast Regex
        Matcher matcher = SSN_PATTERN.matcher(code);
        if (matcher.find()) return true;

        // Tier 2: AI Reasoning (Reuse same scan but look for PII keywords)
        // In production, we'd have specialized PII AI prompts.
        return false; // AI scanning logic for PII could be added similarly
    }
}
