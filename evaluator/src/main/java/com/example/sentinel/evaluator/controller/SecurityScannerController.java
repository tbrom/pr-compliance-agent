package com.example.sentinel.evaluator.controller;

import com.example.sentinel.evaluator.service.SecurityScannerService;
import org.springframework.web.bind.annotation.*;

import java.util.HashMap;
import java.util.Map;

@RestController
@RequestMapping("/api/scan")
public class SecurityScannerController {

    private final SecurityScannerService scanner;

    public SecurityScannerController(SecurityScannerService scanner) {
        this.scanner = scanner;
    }

    @PostMapping
    public Map<String, Object> scan(@RequestBody Map<String, String> request) {
        String code = request.getOrDefault("code", "");

        boolean hasSecrets = scanner.scanForSecrets(code);
        boolean hasPii = scanner.scanForPii(code);

        Map<String, Object> response = new HashMap<>();
        response.put("has_secrets", hasSecrets);
        response.put("has_pii", hasPii);
        response.put("pass", !hasSecrets && !hasPii);

        return response;
    }

    @GetMapping("/health")
    public Map<String, String> health() {
        return Map.of("status", "healthy");
    }
}
