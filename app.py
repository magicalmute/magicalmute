from flask import Flask, render_template, request, flash, redirect, url_for, jsonify, abort
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from functools import wraps
import os
import json

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'  # Change this to a secure secret key
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///blog.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    posts = db.relationship('Post', backref='author', lazy=True)
    comments = db.relationship('Comment', backref='author', lazy=True)
    likes = db.relationship('Like', backref='user', lazy=True)
    posts = db.relationship('Post', backref='author', lazy=True)

class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text, nullable=False)
    date_posted = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    likes = db.relationship('Like', backref='post', lazy=True)
    comments = db.relationship('Comment', backref='post', lazy=True)

class Like(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)

class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    date_posted = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            return abort(403)
        return f(*args, **kwargs)
    return decorated_function

# Admin Routes
@app.route('/admin')
@login_required
@admin_required
def admin_dashboard():
    stats = {
        'total_posts': Post.query.count(),
        'total_users': User.query.count(),
        'total_comments': Comment.query.count(),
        'recent_posts': Post.query.order_by(Post.date_posted.desc()).limit(5).all(),
        'recent_comments': Comment.query.order_by(Comment.date_posted.desc()).limit(5).all()
    }
    return render_template('admin.html', stats=stats)

@app.route('/admin/posts')
@login_required
@admin_required
def admin_posts():
    page = request.args.get('page', 1, type=int)
    posts = Post.query.order_by(Post.date_posted.desc()).paginate(page=page, per_page=10)
    return jsonify({
        'posts': [{
            'id': post.id,
            'title': post.title,
            'author': post.author.username,
            'date': post.date_posted.strftime('%Y-%m-%d'),
            'likes': len(post.likes),
            'comments': len(post.comments)
        } for post in posts.items],
        'has_next': posts.has_next,
        'has_prev': posts.has_prev,
        'total_pages': posts.pages
    })

@app.route('/admin/post/<int:post_id>', methods=['DELETE'])
@login_required
@admin_required
def delete_post(post_id):
    post = Post.query.get_or_404(post_id)
    db.session.delete(post)
    db.session.commit()
    return jsonify({'success': True})

@app.route('/admin/users')
@login_required
@admin_required
def admin_users():
    users = User.query.all()
    return jsonify([{
        'id': user.id,
        'username': user.username,
        'email': user.email,
        'is_admin': user.is_admin,
        'post_count': len(user.posts)
    } for user in users])

@app.route('/admin/user/<int:user_id>', methods=['PUT'])
@login_required
@admin_required
def update_user(user_id):
    user = User.query.get_or_404(user_id)
    data = request.get_json()
    
    if 'is_admin' in data:
        user.is_admin = data['is_admin']
    
    db.session.commit()
    return jsonify({'success': True})

@app.route('/admin/comments')
@login_required
@admin_required
def admin_comments():
    comments = Comment.query.order_by(Comment.date_posted.desc()).all()
    return jsonify([{
        'id': comment.id,
        'content': comment.content,
        'author': comment.author.username,
        'post_title': comment.post.title,
        'date': comment.date_posted.strftime('%Y-%m-%d')
    } for comment in comments])

@app.route('/admin/comment/<int:comment_id>', methods=['DELETE'])
@login_required
@admin_required
def delete_comment(comment_id):
    comment = Comment.query.get_or_404(comment_id)
    db.session.delete(comment)
    db.session.commit()
    return jsonify({'success': True})

@app.route('/admin/profile', methods=['GET', 'PUT'])
@login_required
@admin_required
def admin_profile():
    if request.method == 'GET':
        return jsonify({
            'username': current_user.username,
            'email': current_user.email,
            'post_count': len(current_user.posts),
            'join_date': current_user.date_joined.strftime('%Y-%m-%d') if hasattr(current_user, 'date_joined') else 'N/A'
        })
    
    if request.method == 'PUT':
        data = request.get_json()
        if 'email' in data:
            # Check if email is already taken by another user
            existing_user = User.query.filter(User.email == data['email'], User.id != current_user.id).first()
            if existing_user:
                return jsonify({'success': False, 'error': 'Email already taken'}), 400
            current_user.email = data['email']
            
        if 'current_password' in data and 'new_password' in data:
            if not check_password_hash(current_user.password_hash, data['current_password']):
                return jsonify({'success': False, 'error': 'Current password is incorrect'}), 400
            current_user.password_hash = generate_password_hash(data['new_password'])
            
        db.session.commit()
        return jsonify({'success': True})

@app.route('/admin/settings', methods=['GET', 'PUT'])
@login_required
@admin_required
def admin_settings():
    settings_file = os.path.join(app.root_path, 'settings.json')
    
    if request.method == 'GET':
        if os.path.exists(settings_file):
            with open(settings_file, 'r') as f:
                return jsonify(json.load(f))
        return jsonify({
            'site_name': 'ModernBlog',
            'posts_per_page': 10,
            'allow_comments': True,
            'allow_registration': True,
            'email_notifications': False,
            'theme': 'light'
        })
    
    if request.method == 'PUT':
        settings = request.get_json()
        with open(settings_file, 'w') as f:
            json.dump(settings, f, indent=4)
        return jsonify({'success': True})

# Routes
@app.route('/')
def home():
    page = request.args.get('page', 1, type=int)
    posts = Post.query.order_by(Post.date_posted.desc()).paginate(page=page, per_page=5)
    return render_template('home.html', posts=posts)

@app.route('/blog')
def blog():
    page = request.args.get('page', 1, type=int)
    posts = Post.query.order_by(Post.date_posted.desc()).paginate(page=page, per_page=10)
    return render_template('blog.html', posts=posts)

@app.route('/post/<int:post_id>')
def post(post_id):
    post = Post.query.get_or_404(post_id)
    return render_template('post.html', post=post)

@app.route('/create_post', methods=['GET', 'POST'])
@login_required
def create_post():
    if request.method == 'POST':
        title = request.form.get('title')
        content = request.form.get('content')
        
        if not title or not content:
            flash('Title and content are required!', 'danger')
            return redirect(url_for('create_post'))
            
        post = Post(title=title, content=content, author=current_user)
        db.session.add(post)
        db.session.commit()
        flash('Your post has been created!', 'success')
        return redirect(url_for('blog'))
        
    return render_template('create_post.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        
        if User.query.filter_by(username=username).first():
            flash('Username already exists!', 'danger')
            return redirect(url_for('register'))
            
        if User.query.filter_by(email=email).first():
            flash('Email already registered!', 'danger')
            return redirect(url_for('register'))
            
        user = User(
            username=username,
            email=email,
            password_hash=generate_password_hash(password)
        )
        db.session.add(user)
        db.session.commit()
        flash('Registration successful!', 'success')
        return redirect(url_for('login'))
        
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            next_page = request.args.get('next')
            
            # If user is admin and trying to access admin panel, redirect there
            if user.is_admin and next_page and 'admin' in next_page:
                return redirect(next_page)
            # Otherwise redirect to home
            return redirect(url_for('home'))
        else:
            flash('Invalid username or password!', 'danger')
            
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('home'))

@app.route('/like/<int:post_id>', methods=['POST'])
@login_required
def like_post(post_id):
    post = Post.query.get_or_404(post_id)
    like = Like.query.filter_by(user_id=current_user.id, post_id=post_id).first()
    
    if like:
        db.session.delete(like)
        db.session.commit()
    else:
        like = Like(user_id=current_user.id, post_id=post_id)
        db.session.add(like)
        db.session.commit()
        
    return jsonify({
        'success': True,
        'likes': len(post.likes)
    })

@app.route('/comment/<int:post_id>', methods=['POST'])
@login_required
def add_comment(post_id):
    data = request.get_json()
    content = data.get('content')
    
    if not content:
        return jsonify({'success': False, 'error': 'Comment cannot be empty'})
        
    comment = Comment(
        content=content,
        user_id=current_user.id,
        post_id=post_id
    )
    db.session.add(comment)
    db.session.commit()
    
    return jsonify({'success': True})

if __name__ == '__main__':
    db.create_all()
    app.run(debug=True)