from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import json
import os
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'  # use env variable in production

# Load tools
with open(os.path.join('data', 'ai_tools_database.json'), 'r') as f:
    tools_data = json.load(f)['ai_tools']

# --- SIGNUP ---
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = generate_password_hash(request.form['password'])

        conn = sqlite3.connect('users.db')
        cursor = conn.cursor()
        try:
            cursor.execute("INSERT INTO users (name, email, password) VALUES (?, ?, ?)", (name, email, password))
            conn.commit()
        except sqlite3.IntegrityError:
            return render_template('signup.html', error="Email already exists.")
        finally:
            conn.close()

        return redirect(url_for('login'))

    return render_template('signup.html')

# --- LOGIN ---
@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        conn = sqlite3.connect('users.db')
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, password FROM users WHERE email = ?", (email,))
        user = cursor.fetchone()
        conn.close()

        if user and check_password_hash(user[2], password):
            session['user'] = {'id': user[0], 'email': email, 'name': user[1]}
            return redirect(url_for('dashboard'))
        else:
            return render_template('login.html', error="Invalid email or password")

    if 'user' in session:
        return redirect(url_for('dashboard'))
    return render_template('login.html')

# --- LOGOUT ---
@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))

# --- DASHBOARD ---
@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        return redirect(url_for('login'))
    return render_template('dashboard.html', tools=tools_data, user=session['user'])
    


# --- SEARCH ---
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

# --- TOOL DETAIL ---
@app.route('/tool/<tool_name>')
def tool_detail(tool_name):
    if 'user' not in session:
        return redirect(url_for('login'))

    tool = next((t for t in tools_data if t['name'].lower() == tool_name.lower()), None)
    if not tool:
        return "Tool not found", 404

    # Track tool visit in tool_views table
    user_id = session['user']['id']
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO tool_views (user_id, tool_name)
        VALUES (?, ?)
    """, (user_id, tool_name))

    # Keep only last 11 visits for the user
    cursor.execute("""
        DELETE FROM tool_views
        WHERE id NOT IN (
            SELECT id FROM tool_views
            WHERE user_id = ?
            ORDER BY viewed_at DESC
            LIMIT 11
        ) AND user_id = ?
    """, (user_id, user_id))

    # Fetch reviews
    cursor.execute("""
        SELECT id, user_name, user_id, content, created_at, likes, dislikes
        FROM reviews
        WHERE tool_name = ?
        ORDER BY likes DESC, created_at DESC
    """, (tool_name,))
    reviews = cursor.fetchall()

    conn.commit()
    conn.close()

    return render_template('detail.html', tool=tool, reviews=reviews, user=session['user'])

    
    from flask import jsonify
import sqlite3
from datetime import datetime

# --- Post or Update a Review ---
@app.route('/tool/<tool_name>/review', methods=['POST'])
def post_review(tool_name):
    if 'user' not in session:
        return redirect(url_for('login'))

    user = session['user']
    content = request.form['review'].strip()

    if not content:
        return redirect(url_for('tool_detail', tool_name=tool_name))

    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()

    # Check if user already reviewed this tool
    cursor.execute("SELECT id FROM reviews WHERE tool_name = ? AND user_id = ?", (tool_name, user['id']))
    existing = cursor.fetchone()

    if existing:
        cursor.execute("UPDATE reviews SET content = ?, created_at = CURRENT_TIMESTAMP WHERE id = ?", (content, existing[0]))
    else:
        cursor.execute("INSERT INTO reviews (tool_name, user_id, user_name, content) VALUES (?, ?, ?, ?)",
                       (tool_name, user['id'], user['name'], content))

    conn.commit()
    conn.close()

    return redirect(url_for('tool_detail', tool_name=tool_name))

# --- Delete Review ---
@app.route('/review/<int:review_id>/delete', methods=['POST'])
def delete_review(review_id):
    if 'user' not in session:
        return redirect(url_for('login'))

    user_id = session['user']['id']
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute("DELETE FROM reviews WHERE id = ? AND user_id = ?", (review_id, user_id))
    conn.commit()
    conn.close()

    return jsonify(success=True)

@app.route('/review/<int:review_id>/<string:action>', methods=['POST'])
def vote_review(review_id, action):
    if 'user' not in session or action not in ['like', 'dislike']:
        return jsonify({'success': False})

    user_id = session['user']['id']
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()

    # Check existing vote
    cursor.execute("SELECT vote_type FROM review_votes WHERE user_id = ? AND review_id = ?", (user_id, review_id))
    existing = cursor.fetchone()

    if existing:
        if existing[0] == action:
            # Same vote again → remove
            cursor.execute("DELETE FROM review_votes WHERE user_id = ? AND review_id = ?", (user_id, review_id))
            cursor.execute(f"UPDATE reviews SET {action}s = {action}s - 1 WHERE id = ?", (review_id,))
        else:
            # Switch vote
            cursor.execute("UPDATE review_votes SET vote_type = ? WHERE user_id = ? AND review_id = ?", (action, user_id, review_id))
            cursor.execute(f"UPDATE reviews SET {action}s = {action}s + 1 WHERE id = ?", (review_id,))
            opposite = 'like' if action == 'dislike' else 'dislike'
            cursor.execute(f"UPDATE reviews SET {opposite}s = {opposite}s - 1 WHERE id = ?", (review_id,))
    else:
        # New vote
        cursor.execute("INSERT INTO review_votes (user_id, review_id, vote_type) VALUES (?, ?, ?)", (user_id, review_id, action))
        cursor.execute(f"UPDATE reviews SET {action}s = {action}s + 1 WHERE id = ?", (review_id,))

    conn.commit()
    conn.close()
    return jsonify({'success': True})

    
@app.route('/tool/<tool_name>/review', methods=['POST'])
def submit_review(tool_name):
    if 'user' not in session:
        return redirect(url_for('login'))

    content = request.form['review']
    user = session['user']

    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO reviews (tool_name, user_id, user_name, content) VALUES (?, ?, ?, ?)",
        (tool_name, user['id'], user['name'], content)
    )
    conn.commit()
    conn.close()

    return redirect(url_for('tool_detail', tool_name=tool_name))


@app.route('/history')
def history():
    if 'user' not in session:
        return redirect(url_for('login'))

    user_id = session['user']['id']
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute("""
        SELECT tool_name, viewed_at
        FROM tool_views
        WHERE user_id = ?
        ORDER BY viewed_at DESC
        LIMIT 11
    """, (user_id,))
    views = cursor.fetchall()
    conn.close()

    # Get full tool details using tool_name
    visited_tools = [tool for name, _ in views for tool in tools_data if tool['name'].lower() == name.lower()]
    return render_template('history.html', tools=visited_tools, user=session['user'])


# --- START APP ---
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=True, host='0.0.0.0', port=port)

