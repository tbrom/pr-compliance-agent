package com.example.sentinel.evaluator.service;

import dev.langchain4j.service.SystemMessage;
import dev.langchain4j.service.UserMessage;
import dev.langchain4j.service.spring.AiService;

@AiService
public interface SecurityAIService {

    @SystemMessage("""
        You are a Principal Security Engineer. Your task is to analyze the following code for security risks.
        Look for:
        1. Hardcoded credentials (passwords, API keys, tokens) that are not caught by simple regex.
        2. Exposure of PII or sensitive data.
        3. Insecure cryptographic practices.
        
        If you find a risk, describe it briefly. If no risks are found, simply say 'COMPLIANT'.
    """)
    String scan(@UserMessage String code);
}
