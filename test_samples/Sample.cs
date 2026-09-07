using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.Extensions.Logging;

namespace AutoFmea.Services
{
    /// <summary>
    /// UserService — Manages user accounts and authentication.
    /// Depended on by AuthController, SessionManager, and ReportService.
    /// </summary>
    public class UserService
    {
        private readonly IUserRepository _userRepository;
        private readonly ILogger<UserService> _logger;
        private readonly int _sessionTtl;

        public UserService(IUserRepository userRepository, ILogger<UserService> logger)
        {
            _userRepository = userRepository ?? throw new ArgumentNullException(nameof(userRepository));
            _logger = logger ?? throw new ArgumentNullException(nameof(logger));
            _sessionTtl = 3600;
        }

        public async Task<User?> GetUserAsync(int userId)
        {
            if (userId <= 0)
                throw new ArgumentException("User ID must be positive.", nameof(userId));

            try
            {
                return await _userRepository.FindByIdAsync(userId);
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Failed to retrieve user {UserId}", userId);
                throw;
            }
        }

        public async Task<User> CreateUserAsync(string username, string email, string role = "user")
        {
            if (string.IsNullOrWhiteSpace(username) || username.Length < 3)
                throw new ArgumentException("Username must be at least 3 characters.");

            if (!email.Contains('@'))
                throw new ArgumentException("Invalid email address.");

            var validRoles = new[] { "user", "admin", "moderator" };
            if (!validRoles.Contains(role))
                throw new ArgumentException($"Invalid role: {role}");

            if (await _userRepository.ExistsByEmailAsync(email))
                throw new InvalidOperationException("A user with this email already exists.");

            var user = new User
            {
                Username = username,
                Email = email,
                Role = role,
                CreatedAt = DateTime.UtcNow
            };

            return await _userRepository.SaveAsync(user);
        }

        public async Task<bool> DeleteUserAsync(int userId, int requestingUserId)
        {
            var requestor = await GetUserAsync(requestingUserId);
            if (requestor == null || requestor.Role != "admin")
                throw new UnauthorizedAccessException("Only admins can delete users.");

            var target = await GetUserAsync(userId);
            if (target == null) return false;

            await _userRepository.DeleteByIdAsync(userId);
            return true;
        }

        private bool IsValidPassword(string password)
        {
            if (string.IsNullOrEmpty(password) || password.Length < 8) return false;
            bool hasUpper = password.Any(char.IsUpper);
            bool hasDigit = password.Any(char.IsDigit);
            return hasUpper && hasDigit;
        }
    }

    /// <summary>
    /// DataProcessor — Processes raw data records through a validation pipeline.
    /// </summary>
    public class DataProcessor
    {
        private readonly List<string> _errors = new();
        private int _processedCount;

        public List<string> ProcessBatch(List<string> records)
        {
            var results = new List<string>();

            for (int i = 0; i < records.Count; i++)
            {
                var record = records[i];

                if (string.IsNullOrWhiteSpace(record))
                {
                    _errors.Add($"Record {i}: empty record.");
                    continue;
                }

                try
                {
                    var validated = Validate(record);
                    var transformed = Transform(validated);
                    results.Add(transformed);
                    _processedCount++;
                }
                catch (Exception ex)
                {
                    _errors.Add($"Record {i}: {ex.Message}");
                }
            }

            return results;
        }

        private string Validate(string record)
        {
            if (record.Length > 10000)
                throw new ArgumentException("Record exceeds maximum size.");
            return record.Trim();
        }

        private string Transform(string record)
        {
            return record.ToUpperInvariant();
        }

        public string GetReport()
        {
            return $"Processed: {_processedCount}, Errors: {_errors.Count}";
        }
    }

    /// <summary>
    /// SessionManager — Manages user sessions. Used by UserService.
    /// </summary>
    public class SessionManager
    {
        private readonly Dictionary<string, (object Data, DateTime Created)> _store = new();
        private readonly int _ttl;

        public SessionManager(int ttlSeconds = 3600)
        {
            _ttl = ttlSeconds;
        }

        public void Create(string token, object data)
        {
            _store[token] = (data, DateTime.UtcNow);
        }

        public object? Get(string token)
        {
            if (!_store.TryGetValue(token, out var entry)) return null;
            if ((DateTime.UtcNow - entry.Created).TotalSeconds > _ttl)
            {
                _store.Remove(token);
                return null;
            }
            return entry.Data;
        }

        public void Invalidate(string token)
        {
            _store.Remove(token);
        }
    }
}
