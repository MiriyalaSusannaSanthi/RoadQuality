ROADQUALITY WEB FRONTEND

1. Keep your Flask API running on http://127.0.0.1:5000
2. Extract this folder.
3. Open PowerShell in this folder:
   python -m http.server 5500
4. Open:
   http://127.0.0.1:5500

The frontend calls:
   GET http://127.0.0.1:5000/health
   GET http://127.0.0.1:5000/analyze?source=...&destination=...&preference=...

If your API uses a different analyze route or JSON field names, send me the exact API response and I will adapt app.js.
