# Python-Proxy Server

This is a multithreaded HTTP/HTTPS proxy server implemented in Python.  
It was created as a part of a Computer Networks Lab project.

---

## Features

- Supports **HTTP and HTTPS (via CONNECT tunneling)**
- Parses and modifies request and response headers
- Converts HTTP/1.1 to HTTP/1.0 to simplify connection handling
- Closes persistent connections for clean termination
- Handles multiple clients using a `ThreadPoolExecutor`

---

## 🚀 Getting Started

### 📦 Requirements

- Python 3.7+
- No external dependencies

### 🖥️ Running the Proxy

```bash
python proxy_server.py
```
The proxy listens on localhost:8080 by default.

## 🧪 Testing

### HTTP:
```bash
curl -x http://127.0.0.1:8080 http://example.com
```

### HTTPS:
```bash
curl -x http://127.0.0.1:8080 https://www.google.com -k
```

## Repository Structure

| File | Description |
|------|-------------|
| `proxy_server.py` | Main proxy server implementation |
| `README.md` | Project overview and usage guide |

## Contact

For any questions, suggestions, or issues, please contact:

- **Email:** arnavkaducr7@gmail.com

Feel free to reach out if you need any assistance!
