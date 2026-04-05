package com.example.sentinel.evaluator.service;

import org.springframework.stereotype.Service;
import java.util.regex.Pattern;
import java.util.regex.Matcher;

@Service
public class SecurityScannerService {

    private static final Pattern AWS_KEY_PATTERN = Pattern.compile("AKIA[0-9A-Z]{16}");
    private static final Pattern SSN_PATTERN = Pattern.compile("\\d{3}-\\d{2}-\\d{4}");

    public boolean scanForSecrets(String code) {
        if (code == null) return false;
        Matcher matcher = AWS_KEY_PATTERN.matcher(code);
        return matcher.find();
    }

    public boolean scanForPii(String code) {
        if (code == null) return false;
        Matcher matcher = SSN_PATTERN.matcher(code);
        return matcher.find();
    }
}
