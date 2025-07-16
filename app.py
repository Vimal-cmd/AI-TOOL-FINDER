from flask import Flask, render_template, request, redirect, url_for, session
import json
import os

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'  # use env variable in production

# Load tools
with open(os.path.join('data', 'ai_tools_database.json'), 'r') as f:
    tools_data = json.load(f)['ai_tools']

# Dummy user database
USERS = {
    "user@example.com": {
        "password": "secret123",
        "name": "Vimal"
    }
}

@app.route('/')
def login():
    if 'user' in session:
        return redirect(url_for('dashboard'))
    return render_template('login.html')

@app.route('/login', methods=['POST'])
def do_login():
    email = request.form['email']
    password = request.form['password']

    user = USERS.get(email)
    if user and user['password'] == password:
        session['user'] = {'email': email, 'name': user['name']}
        return redirect(url_for('dashboard'))
    else:
        return render_template('login.html', error="Invalid email or password")

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))

@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        return redirect(url_for('login'))
    return render_template('dashboard.html', tools=tools_data, user=session['user'])

@app.route('/search')
def search():
    query = request.args.get('q', '').lower()
    results = []
    for tool in tools_data:
        if (query in tool['name'].lower() or
            query in tool['description'].lower() or
            any(query in cat.lower() for cat in tool.get('categories', [])) or
            any(query in feat.lower() for feat in tool.get('features', []))):
            results.append(tool)
    return json.dumps(results)

@app.route('/tool/<tool_name>')
def tool_detail(tool_name):
    if 'user' not in session:
        return redirect(url_for('login'))

    for tool in tools_data:
        if tool['name'].lower() == tool_name.lower():
            return render_template('detail.html', tool=tool)
    return "Tool not found", 404

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=True, host='0.0.0.0', port=port)

