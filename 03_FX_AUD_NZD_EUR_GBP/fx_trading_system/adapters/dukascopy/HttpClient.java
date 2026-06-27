package adapters.dukascopy;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.Map;

/**
 * Lightweight HTTP client for communicating with the Python FastAPI backend.
 * Uses java.net.HttpURLConnection -- no external dependencies required.
 */
public class HttpClient {

    private final String baseUrl;
    private final int connectTimeoutMs;
    private final int readTimeoutMs;

    /**
     * @param baseUrl          Root URL of the Python backend, e.g. "http://localhost:8000"
     * @param connectTimeoutMs Connection timeout in milliseconds
     * @param readTimeoutMs    Read timeout in milliseconds
     */
    public HttpClient(String baseUrl, int connectTimeoutMs, int readTimeoutMs) {
        // Strip trailing slash
        this.baseUrl = baseUrl.endsWith("/") ? baseUrl.substring(0, baseUrl.length() - 1) : baseUrl;
        this.connectTimeoutMs = connectTimeoutMs;
        this.readTimeoutMs = readTimeoutMs;
    }

    public HttpClient(String baseUrl) {
        this(baseUrl, 5000, 10000);
    }

    // ── Response wrapper ────────────────────────────────────────────────────

    public static class Response {
        private final int statusCode;
        private final String body;

        public Response(int statusCode, String body) {
            this.statusCode = statusCode;
            this.body = body;
        }

        public int getStatusCode() { return statusCode; }
        public String getBody()    { return body; }
        public boolean isOk()      { return statusCode >= 200 && statusCode < 300; }

        /**
         * Crude JSON string-value extraction.  Returns the value for the first
         * occurrence of "key": "value" or "key": number/boolean.
         * For real production use, swap in Jackson or Gson.
         */
        public String jsonValue(String key) {
            if (body == null) return null;
            String search = "\"" + key + "\"";
            int idx = body.indexOf(search);
            if (idx == -1) return null;
            int colonIdx = body.indexOf(':', idx + search.length());
            if (colonIdx == -1) return null;
            int start = colonIdx + 1;
            // Skip whitespace
            while (start < body.length() && body.charAt(start) == ' ') start++;
            if (start >= body.length()) return null;

            char first = body.charAt(start);
            if (first == '"') {
                // String value
                int end = body.indexOf('"', start + 1);
                if (end == -1) return null;
                return body.substring(start + 1, end);
            } else if (first == '{' || first == '[') {
                // Object or array -- find matching close bracket
                char open = first;
                char close = (open == '{') ? '}' : ']';
                int depth = 1;
                int pos = start + 1;
                boolean inString = false;
                while (pos < body.length() && depth > 0) {
                    char c = body.charAt(pos);
                    if (inString) {
                        if (c == '\\') { pos++; }  // skip escaped char
                        else if (c == '"') { inString = false; }
                    } else {
                        if (c == '"') { inString = true; }
                        else if (c == open) { depth++; }
                        else if (c == close) { depth--; }
                    }
                    pos++;
                }
                return body.substring(start, pos);
            } else {
                // Number, boolean, null
                int end = start;
                while (end < body.length() && body.charAt(end) != ',' && body.charAt(end) != '}'
                        && body.charAt(end) != ']' && body.charAt(end) != '\n') {
                    end++;
                }
                return body.substring(start, end).trim();
            }
        }

        /**
         * Returns true if the JSON body contains "key": true (boolean true).
         */
        public boolean jsonBoolean(String key) {
            String val = jsonValue(key);
            return "true".equalsIgnoreCase(val);
        }

        /**
         * Returns a double from a JSON numeric field, or the default if missing.
         */
        public double jsonDouble(String key, double defaultValue) {
            String val = jsonValue(key);
            if (val == null) return defaultValue;
            try {
                return Double.parseDouble(val);
            } catch (NumberFormatException e) {
                return defaultValue;
            }
        }

        /**
         * Returns an int from a JSON numeric field, or the default if missing.
         */
        public int jsonInt(String key, int defaultValue) {
            String val = jsonValue(key);
            if (val == null) return defaultValue;
            try {
                return (int) Double.parseDouble(val);
            } catch (NumberFormatException e) {
                return defaultValue;
            }
        }

        @Override
        public String toString() {
            return "Response{status=" + statusCode + ", body=" + (body != null ? body.substring(0, Math.min(body.length(), 200)) : "null") + "}";
        }
    }

    // ── Public API ──────────────────────────────────────────────────────────

    /**
     * Perform an HTTP GET request.
     *
     * @param path API path, e.g. "/api/health"
     * @return Response object, or null if the request failed due to connectivity
     */
    public Response get(String path) {
        HttpURLConnection conn = null;
        try {
            URL url = new URL(baseUrl + path);
            conn = (HttpURLConnection) url.openConnection();
            conn.setRequestMethod("GET");
            conn.setRequestProperty("Accept", "application/json");
            conn.setConnectTimeout(connectTimeoutMs);
            conn.setReadTimeout(readTimeoutMs);

            int status = conn.getResponseCode();
            String body = readStream(conn, status);
            return new Response(status, body);
        } catch (IOException e) {
            return null;  // Backend unreachable
        } finally {
            if (conn != null) conn.disconnect();
        }
    }

    /**
     * Perform an HTTP POST request with a JSON body.
     *
     * @param path    API path, e.g. "/api/broker/tick"
     * @param jsonBody JSON string to send as the request body
     * @return Response object, or null if the request failed due to connectivity
     */
    public Response post(String path, String jsonBody) {
        HttpURLConnection conn = null;
        try {
            URL url = new URL(baseUrl + path);
            conn = (HttpURLConnection) url.openConnection();
            conn.setRequestMethod("POST");
            conn.setRequestProperty("Content-Type", "application/json");
            conn.setRequestProperty("Accept", "application/json");
            conn.setConnectTimeout(connectTimeoutMs);
            conn.setReadTimeout(readTimeoutMs);
            conn.setDoOutput(true);

            byte[] payload = jsonBody.getBytes(StandardCharsets.UTF_8);
            conn.setFixedLengthStreamingMode(payload.length);
            try (OutputStream os = conn.getOutputStream()) {
                os.write(payload);
                os.flush();
            }

            int status = conn.getResponseCode();
            String body = readStream(conn, status);
            return new Response(status, body);
        } catch (IOException e) {
            return null;  // Backend unreachable
        } finally {
            if (conn != null) conn.disconnect();
        }
    }

    /**
     * Perform an HTTP PUT request with a JSON body.
     *
     * @param path     API path
     * @param jsonBody JSON string to send
     * @return Response object, or null on connectivity failure
     */
    public Response put(String path, String jsonBody) {
        HttpURLConnection conn = null;
        try {
            URL url = new URL(baseUrl + path);
            conn = (HttpURLConnection) url.openConnection();
            conn.setRequestMethod("PUT");
            conn.setRequestProperty("Content-Type", "application/json");
            conn.setRequestProperty("Accept", "application/json");
            conn.setConnectTimeout(connectTimeoutMs);
            conn.setReadTimeout(readTimeoutMs);
            conn.setDoOutput(true);

            byte[] payload = jsonBody.getBytes(StandardCharsets.UTF_8);
            conn.setFixedLengthStreamingMode(payload.length);
            try (OutputStream os = conn.getOutputStream()) {
                os.write(payload);
                os.flush();
            }

            int status = conn.getResponseCode();
            String body = readStream(conn, status);
            return new Response(status, body);
        } catch (IOException e) {
            return null;
        } finally {
            if (conn != null) conn.disconnect();
        }
    }

    /**
     * Check if the backend is reachable by hitting the health endpoint.
     */
    public boolean isBackendHealthy() {
        Response resp = get("/api/health");
        return resp != null && resp.isOk();
    }

    // ── JSON builder helpers ────────────────────────────────────────────────

    /**
     * Build a simple flat JSON object from key-value pairs.
     * Values are auto-typed: numbers and booleans are unquoted, strings are quoted.
     */
    public static String jsonObject(Object... keyValuePairs) {
        if (keyValuePairs.length % 2 != 0) {
            throw new IllegalArgumentException("Must supply an even number of arguments (key-value pairs)");
        }
        StringBuilder sb = new StringBuilder("{");
        for (int i = 0; i < keyValuePairs.length; i += 2) {
            if (i > 0) sb.append(",");
            String key = String.valueOf(keyValuePairs[i]);
            Object val = keyValuePairs[i + 1];
            sb.append("\"").append(escapeJson(key)).append("\":");
            if (val == null) {
                sb.append("null");
            } else if (val instanceof Number || val instanceof Boolean) {
                sb.append(val);
            } else {
                sb.append("\"").append(escapeJson(String.valueOf(val))).append("\"");
            }
        }
        sb.append("}");
        return sb.toString();
    }

    private static String escapeJson(String s) {
        return s.replace("\\", "\\\\")
                .replace("\"", "\\\"")
                .replace("\n", "\\n")
                .replace("\r", "\\r")
                .replace("\t", "\\t");
    }

    // ── Internals ───────────────────────────────────────────────────────────

    private String readStream(HttpURLConnection conn, int statusCode) throws IOException {
        BufferedReader reader;
        if (statusCode >= 200 && statusCode < 400) {
            reader = new BufferedReader(new InputStreamReader(conn.getInputStream(), StandardCharsets.UTF_8));
        } else {
            if (conn.getErrorStream() != null) {
                reader = new BufferedReader(new InputStreamReader(conn.getErrorStream(), StandardCharsets.UTF_8));
            } else {
                return "";
            }
        }
        StringBuilder sb = new StringBuilder();
        String line;
        while ((line = reader.readLine()) != null) {
            sb.append(line);
        }
        reader.close();
        return sb.toString();
    }
}
