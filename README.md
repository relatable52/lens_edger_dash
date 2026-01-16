# How to run from source

This instruction if for running on Windows.

First install `uv`. 

Open the terminal from the root of the project folder and type

```
winget install --id=astral-sh.uv  -e
```

Then run 

```
uv sync && uv run main.py
```

You should see this printed on the terminal

```
Dash is running on http://0.0.0.0:8050/

 * Serving Flask app 'main'
 * Debug mode: off
WARNING: This is a development server. Do not use it in a production deployment. Use a production WSGI server instead.
 * Running on all addresses (0.0.0.0)
 * Running on http://127.0.0.1:8050
 * Running on http://192.168.100.193:8050
Press CTRL+C to quit
```

Open web browser and visit [http://127.0.0.1:8050](http://127.0.0.1:8050) to see the application.
