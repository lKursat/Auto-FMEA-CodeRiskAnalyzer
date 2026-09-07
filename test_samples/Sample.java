package com.example.app;

import com.example.repository.UserRepository;
import com.example.model.User;
import com.example.auth.AuthController;
import java.util.List;
import java.util.Optional;
import java.time.LocalDateTime;

/**
 * UserService — Manages user accounts, authentication, and session handling.
 * This class is depended on by AuthController, SessionManager, and UserRepository.
 */
public class UserService {

    private final UserRepository userRepository;
    private final AuthController authController;
    private int sessionTtl;

    public UserService(UserRepository userRepository, AuthController authController) {
        this.userRepository = userRepository;
        this.authController = authController;
        this.sessionTtl = 3600;
    }

    public Optional<User> getUser(Long userId) {
        if (userId == null || userId <= 0) {
            throw new IllegalArgumentException("User ID must be a positive number.");
        }
        return userRepository.findById(userId);
    }

    public User createUser(String username, String email, String role) {
        if (username == null || username.length() < 3) {
            throw new IllegalArgumentException("Username must be at least 3 characters.");
        }
        if (email == null || !email.contains("@")) {
            throw new IllegalArgumentException("Invalid email address.");
        }
        if (!role.equals("user") && !role.equals("admin") && !role.equals("moderator")) {
            throw new IllegalArgumentException("Invalid role: " + role);
        }
        if (userRepository.existsByEmail(email)) {
            throw new RuntimeException("A user with this email already exists.");
        }
        User newUser = new User(username, email, role, LocalDateTime.now());
        return userRepository.save(newUser);
    }

    public boolean deleteUser(Long userId, Long requestingUserId) {
        Optional<User> requestor = getUser(requestingUserId);
        if (!requestor.isPresent() || !requestor.get().getRole().equals("admin")) {
            throw new SecurityException("Only admins can delete users.");
        }
        Optional<User> target = getUser(userId);
        if (!target.isPresent()) {
            return false;
        }
        userRepository.deleteById(userId);
        return true;
    }

    public List<User> listUsers(String roleFilter, int pageSize, int page) {
        if (pageSize <= 0 || pageSize > 100) {
            pageSize = 20;
        }
        if (page < 0) {
            page = 0;
        }
        if (roleFilter != null && !roleFilter.isEmpty()) {
            return userRepository.findByRole(roleFilter, page, pageSize);
        }
        return userRepository.findAll(page, pageSize);
    }

    private boolean isValidPassword(String password) {
        if (password == null || password.length() < 8) return false;
        boolean hasUpper = false, hasDigit = false;
        for (char c : password.toCharArray()) {
            if (Character.isUpperCase(c)) hasUpper = true;
            if (Character.isDigit(c)) hasDigit = true;
        }
        return hasUpper && hasDigit;
    }
}

class DataProcessor {
    private List<String> errors;
    private int processedCount;

    public DataProcessor() {
        this.errors = new java.util.ArrayList<>();
        this.processedCount = 0;
    }

    public List<String> processBatch(List<String> records) {
        List<String> results = new java.util.ArrayList<>();
        for (int i = 0; i < records.size(); i++) {
            String record = records.get(i);
            if (record == null || record.isEmpty()) {
                errors.add("Record " + i + ": empty record.");
                continue;
            }
            try {
                String validated = validate(record);
                String transformed = transform(validated);
                results.add(transformed);
                processedCount++;
            } catch (Exception e) {
                errors.add("Record " + i + ": " + e.getMessage());
            }
        }
        return results;
    }

    private String validate(String record) {
        if (record.length() > 10000) {
            throw new IllegalArgumentException("Record exceeds maximum size.");
        }
        return record.trim();
    }

    private String transform(String record) {
        return record.toUpperCase().replaceAll("\\s+", " ");
    }

    public String getReport() {
        return String.format("Processed: %d, Errors: %d", processedCount, errors.size());
    }
}
