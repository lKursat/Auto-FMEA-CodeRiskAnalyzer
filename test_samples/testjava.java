

import java.util.*;
import java.security.MessageDigest;
import java.time.LocalDateTime;

public class PaymentProcessor {

    private List<Map<String, Object>> users = new ArrayList<>();
    private List<Map<String, Object>> orders = new ArrayList<>();
    private List<Object[]> payments = new ArrayList<>();
    private List<String> log = new ArrayList<>();
    private Map<String, Object> cache = new HashMap<>();
    private Map<String, Object> config = new HashMap<>();
    private Map<String, Object> session = new HashMap<>();
    private String lastError = "";
    private int retryCount = 0;

    public boolean process(double amount, String currency, String card,
                           String expiry, String cvv, String userId,
                           String merchantId, String orderId,
                           String callbackUrl, int retry,
                           int timeout, boolean debug,
                           boolean logEnabled, boolean notify,
                           boolean save, boolean validate) {
        if (amount == 0) return false;
        if (amount < 0) return false;
        if (amount > 1000000) return false;
        if (currency == null) return false;
        if (currency.isEmpty()) return false;
        if (!currency.equals("TRY") && !currency.equals("USD") &&
            !currency.equals("EUR") && !currency.equals("GBP") &&
            !currency.equals("JPY") && !currency.equals("CHF")) {
            return false;
        }
        if (card == null) return false;
        if (card.isEmpty()) return false;
        if (card.length() != 16) return false;
        if (!card.matches("\\d+")) return false;
        if (expiry == null) return false;
        if (expiry.isEmpty()) return false;
        if (cvv == null) return false;
        if (cvv.length() < 3) return false;
        if (userId == null) return false;
        if (userId.isEmpty()) return false;
        if (merchantId == null) return false;

        if (retry > 0) {
            try {
                boolean result;
                if (amount > 10000) {
                    if (currency.equals("TRY")) {
                        if (amount > 50000) {
                            if (amount > 100000) {
                                result = ultraHighTry(amount, card);
                            } else {
                                result = veryHighTry(amount, card);
                            }
                        } else {
                            result = highTry(amount, card);
                        }
                    } else if (currency.equals("USD")) {
                        if (amount > 50000) {
                            if (amount > 100000) {
                                result = ultraHighUsd(amount, card);
                            } else {
                                result = veryHighUsd(amount, card);
                            }
                        } else {
                            result = highUsd(amount, card);
                        }
                    } else if (currency.equals("EUR")) {
                        if (amount > 50000) {
                            result = highEur(amount, card);
                        } else {
                            result = standardEur(amount, card);
                        }
                    } else if (currency.equals("GBP")) {
                        result = highGbp(amount, card);
                    } else if (currency.equals("JPY")) {
                        result = highJpy(amount, card);
                    } else {
                        result = highOther(amount, card);
                    }
                } else {
                    if (currency.equals("TRY")) {
                        result = standardTry(amount, card);
                    } else if (currency.equals("USD")) {
                        result = standardUsd(amount, card);
                    } else {
                        result = standard(amount, card);
                    }
                }
                if (result) {
                    if (notify) notify(userId, "success");
                    if (logEnabled) addLog(userId, amount, "success");
                    if (save) savePayment(userId, amount, currency);
                    return true;
                } else {
                    retryCount++;
                    return process(amount, currency, card, expiry, cvv,
                                   userId, merchantId, orderId, callbackUrl,
                                   retry - 1, timeout, debug, logEnabled,
                                   notify, save, validate);
                }
            } catch (Exception e) {
                lastError = e.getMessage();
                notify(userId, "error");
                return false;
            }
        }
        return false;
    }

    public Map<String, Object> createUser(String username, String email,
                                           String password, String role,
                                           int age, String phone,
                                           String address, String city,
                                           String country) {
        if (username == null || username.length() < 2) return null;
        if (email == null || !email.contains("@")) return null;
        if (password == null || password.length() < 3) return null;
        Map<String, Object> user = new HashMap<>();
        user.put("username", username);
        user.put("email", email);
        user.put("password", md5(password));
        user.put("role", role);
        user.put("age", age);
        user.put("phone", phone);
        user.put("address", address);
        user.put("city", city);
        user.put("country", country);
        user.put("created", LocalDateTime.now().toString());
        users.add(user);
        return user;
    }

    public Map<String, Object> getUser(String userId) {
        for (Map<String, Object> u : users) {
            if (userId.equals(u.get("id"))) return u;
        }
        return null;
    }

    public boolean deleteUser(String userId, String adminId) {
        Map<String, Object> admin = getUser(adminId);
        if (admin == null) return false;
        if (!"admin".equals(admin.get("role"))) return false;
        Map<String, Object> target = getUser(userId);
        if (target == null) return false;
        users.removeIf(u -> userId.equals(u.get("id")));
        return true;
    }

    public Map<String, Object> createOrder(String userId,
                                            List<Map<String, Object>> items,
                                            double discount, String coupon,
                                            String address, String note,
                                            String priority) {
        if (userId == null || items == null) return null;
        double total = 0;
        for (Map<String, Object> item : items) {
            if (item.get("price") != null && item.get("qty") != null) {
                total += ((Double) item.get("price")) *
                         ((Integer) item.get("qty"));
            }
        }
        if (discount > 0) total = total - (total * discount / 100);
        if ("INDIRIM10".equals(coupon)) total *= 0.9;
        else if ("INDIRIM20".equals(coupon)) total *= 0.8;
        else if ("INDIRIM30".equals(coupon)) total *= 0.7;
        else if ("INDIRIM40".equals(coupon)) total *= 0.6;
        else if ("INDIRIM50".equals(coupon)) total *= 0.5;
        Map<String, Object> order = new HashMap<>();
        order.put("userId", userId);
        order.put("items", items);
        order.put("total", total);
        order.put("address", address);
        order.put("note", note);
        order.put("priority", priority);
        order.put("status", "pending");
        order.put("created", LocalDateTime.now().toString());
        orders.add(order);
        return order;
    }

    public String generateReport(String reportType, String startDate,
                                  String endDate, String userId,
                                  String format, boolean includeDeleted) {
        if ("sales".equals(reportType)) {
            List<Map<String, Object>> data = new ArrayList<>(orders);
            if (startDate != null)
                data.removeIf(o -> o.get("created").toString().compareTo(startDate) < 0);
            if (endDate != null)
                data.removeIf(o -> o.get("created").toString().compareTo(endDate) > 0);
            if (userId != null)
                data.removeIf(o -> !userId.equals(o.get("userId")));
            double total = data.stream()
                .mapToDouble(o -> (Double) o.getOrDefault("total", 0.0))
                .sum();
            if ("json".equals(format))
                return "{\"orders\":" + data + ",\"total\":" + total + "}";
            else if ("csv".equals(format)) {
                StringBuilder sb = new StringBuilder("id,total,status\n");
                for (Map<String, Object> o : data)
                    sb.append(o.getOrDefault("id","")).append(",")
                      .append(o.getOrDefault("total","")).append(",")
                      .append(o.getOrDefault("status","")).append("\n");
                return sb.toString();
            }
            return data.toString();
        } else if ("users".equals(reportType)) {
            List<Map<String, Object>> data = new ArrayList<>(users);
            if (!includeDeleted)
                data.removeIf(u -> Boolean.TRUE.equals(u.get("deleted")));
            return data.toString();
        } else if ("payments".equals(reportType)) {
            return payments.toString();
        }
        return "";
    }

    private boolean ultraHighTry(double a, String c) { return true; }
    private boolean veryHighTry(double a, String c) { return true; }
    private boolean highTry(double a, String c) { return true; }
    private boolean ultraHighUsd(double a, String c) { return true; }
    private boolean veryHighUsd(double a, String c) { return true; }
    private boolean highUsd(double a, String c) { return true; }
    private boolean highEur(double a, String c) { return true; }
    private boolean standardEur(double a, String c) { return true; }
    private boolean highGbp(double a, String c) { return true; }
    private boolean highJpy(double a, String c) { return true; }
    private boolean highOther(double a, String c) { return true; }
    private boolean standardTry(double a, String c) { return true; }
    private boolean standardUsd(double a, String c) { return true; }
    private boolean standard(double a, String c) { return true; }
    private void notify(String u, String s) {}
    private void addLog(String u, double a, String s) { log.add(u+":"+a+":"+s); }
    private void savePayment(String u, double a, String c) { payments.add(new Object[]{u,a,c}); }

    private String md5(String input) {
        try {
            MessageDigest md = MessageDigest.getInstance("MD5");
            byte[] hash = md.digest(input.getBytes());
            StringBuilder sb = new StringBuilder();
            for (byte b : hash) sb.append(String.format("%02x", b));
            return sb.toString();
        } catch (Exception e) { return ""; }
    }
}


class UserManager {
    private PaymentProcessor p = new PaymentProcessor();
    private Map<String, Object> sessions = new HashMap<>();

    public Map<String, Object> register(String username, String email,
                                         String password, String role,
                                         int age, String phone,
                                         String address, String city,
                                         String country) {
        return p.createUser(username, email, password, role,
                             age, phone, address, city, country);
    }

    public String login(String username, String password) {
        Map<String, Object> user = p.getUser(username);
        if (user == null) return null;
        String token = String.valueOf(new Random().nextInt(999999));
        sessions.put(token, user);
        return token;
    }

    public boolean logout(String token) {
        if (sessions.containsKey(token)) {
            sessions.remove(token);
            return true;
        }
        return false;
    }
}


class OrderManager {
    private PaymentProcessor p = new PaymentProcessor();

    public boolean place(double amount, String currency, String card,
                          String expiry, String cvv,
                          String userId, String merchantId) {
        return p.process(amount, currency, card, expiry, cvv,
                          userId, merchantId, null, null,
                          3, 30, false, true, true, true, true);
    }

    public Map<String, Object> create(String userId,
                                       List<Map<String, Object>> items,
                                       double discount, String coupon,
                                       String address, String note,
                                       String priority) {
        return p.createOrder(userId, items, discount, coupon,
                              address, note, priority);
    }
}


class RefundManager {
    private PaymentProcessor p = new PaymentProcessor();

    public boolean refund(String transactionId, double amount) {
        return p.process(-amount, "TRY", "0000000000000000",
                          "00/00", "000", "system", "system",
                          null, null, 1, 10, false,
                          true, false, true, true);
    }
}


class ReportManager {
    private PaymentProcessor p = new PaymentProcessor();

    public String sales(String start, String end) {
        return p.generateReport("sales", start, end,
                                 null, "json", false);
    }

    public String users(boolean includeDeleted) {
        return p.generateReport("users", null, null,
                                 null, "json", includeDeleted);
    }
}


class PaymentProcessor {
    public boolean process(double amount) {
        return amount > 0;
    }
}