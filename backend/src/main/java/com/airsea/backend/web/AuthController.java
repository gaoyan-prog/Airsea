package com.airsea.backend.web;

import com.airsea.backend.domain.User;
import com.airsea.backend.repo.UserRepository;
import jakarta.validation.constraints.NotBlank;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

@RestController
@RequestMapping("/auth")
@Validated
public class AuthController {
    private final UserRepository userRepository;

    public AuthController(UserRepository userRepository) {
        this.userRepository = userRepository;
    }

    public record SignupRequest(@NotBlank String username, @NotBlank String password) {}

    public record LoginRequest(String username, String email, @NotBlank String password) {}

    public record UserOut(Long id, String username) {
        public static UserOut of(User u) { return new UserOut(u.getId(), u.getUsername()); }
    }

    @PostMapping("/signup")
    public ResponseEntity<?> signup(@RequestBody SignupRequest req) {
        String uname = req.username().trim();
        if (userRepository.findByUsername(uname).isPresent()) {
            return ResponseEntity.status(HttpStatus.BAD_REQUEST).body(Map.of("detail", "Username already registered"));
        }
        User u = new User();
        u.setUsername(uname);
        u.setPassword(req.password()); // 与现有后端保持明文对比（演示用途）
        userRepository.save(u);
        return ResponseEntity.ok(UserOut.of(u));
    }

    @PostMapping("/login")
    public ResponseEntity<?> login(@RequestBody LoginRequest req) {
        String unameRaw = (req.username() != null ? req.username() : (req.email() != null ? req.email() : ""));
        String uname = unameRaw.trim();
        var userOpt = userRepository.findByUsername(uname);
        if (userOpt.isEmpty()) {
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED).body(Map.of("detail", "User not found"));
        }
        User u = userOpt.get();
        if (!u.getPassword().equals(req.password())) {
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED).body(Map.of("detail", "Password incorrect (plain compare)"));
        }
        return ResponseEntity.ok(UserOut.of(u));
    }
}


