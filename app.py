from flask import Flask, render_template, request, jsonify, session
import json
import os
import random
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data.words import WORDS, LEVEL_1, LEVEL_2, SENTENCES

app = Flask(__name__)
app.secret_key = "plant_english_secret_2024"

DATA_FILE = "data/users.json"

# ── 유저 데이터 ──────────────────────────────────────────────
def load_users():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_users(users):
    os.makedirs("data", exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=2)

def get_user(nickname):
    users = load_users()
    if nickname not in users:
        users[nickname] = {
            "nickname": nickname,
            "score": 0,
            # word_plants: { word: { stage: 0~4, wilted: bool, learned_at: stage } }
            # stage 0=씨앗, 1=새싹, 2=잎, 3=꽃, 4=열매
            "word_plants": {},
            "correct": 0,
            "wrong": 0,
        }
        save_users(users)
    return users[nickname]

def update_user(nickname, data):
    users = load_users()
    users[nickname] = data
    save_users(users)

def get_word_pool(user_data):
    """유저의 단어 진행 상태에 따라 단어 풀 반환"""
    plants = user_data.get("word_plants", {})
    learned_count = len(plants)
    if learned_count < 15:
        return LEVEL_1
    return LEVEL_1 + LEVEL_2

def pick_next_word(user_data):
    """다음에 공부할 단어 선택 (아직 심지 않은 것 우선)"""
    pool = get_word_pool(user_data)
    plants = user_data.get("word_plants", {})
    
    # 시든 것 (wrong으로 wilted된 것) 복습 우선
    wilted = [w for w in pool if w["word"] in plants and plants[w["word"]].get("wilted")]
    if wilted:
        return random.choice(wilted)
    
    # 아직 안 심은 새 단어
    new_words = [w for w in pool if w["word"] not in plants]
    if new_words:
        return random.choice(new_words)
    
    # 성장 중인 단어 (stage < 4)
    growing = [w for w in pool if w["word"] in plants and plants[w["word"]]["stage"] < 4]
    if growing:
        return random.choice(growing)
    
    return random.choice(pool)

def get_word_stage(user_data, word):
    plants = user_data.get("word_plants", {})
    if word not in plants:
        return -1
    return plants[word]["stage"]

# ── 라우트 ────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json()
    nickname = data.get("nickname", "").strip()
    if not nickname or len(nickname) > 10:
        return jsonify({"error": "닉네임을 1~10자로 입력해줘!"}), 400
    user = get_user(nickname)
    session["nickname"] = nickname
    return jsonify({"success": True, "user": user})

@app.route("/api/user")
def get_current_user():
    nickname = session.get("nickname")
    if not nickname:
        return jsonify({"error": "로그인 필요"}), 401
    return jsonify(get_user(nickname))

@app.route("/api/garden")
def get_garden():
    """정원 데이터 반환 - 모든 단어 식물 상태"""
    nickname = session.get("nickname")
    if not nickname:
        return jsonify({"error": "로그인 필요"}), 401
    user = get_user(nickname)
    
    pool = get_word_pool(user)
    garden = []
    for w in pool:
        plant = user["word_plants"].get(w["word"])
        if plant:
            garden.append({
                "word": w["word"],
                "meaning": w["meaning"],
                "stage": plant["stage"],
                "wilted": plant.get("wilted", False),
            })
    return jsonify(garden)

# ── 학습 단계별 API ────────────────────────────────────────────

@app.route("/api/learn/start")
def learn_start():
    """단계 1: 단어 카드 보여주기"""
    nickname = session.get("nickname")
    if not nickname:
        return jsonify({"error": "로그인 필요"}), 401
    user = get_user(nickname)
    word_obj = pick_next_word(user)
    session["current_word"] = word_obj["word"]
    
    plants = user.get("word_plants", {})
    current_stage = plants.get(word_obj["word"], {}).get("stage", -1)
    is_new = word_obj["word"] not in plants
    is_wilted = plants.get(word_obj["word"], {}).get("wilted", False)
    
    return jsonify({
        "word": word_obj["word"],
        "meaning": word_obj["meaning"],
        "stage": current_stage,
        "is_new": is_new,
        "is_wilted": is_wilted,
        "hint": word_obj["word"][0] + "_" * (len(word_obj["word"]) - 1),
    })

@app.route("/api/learn/flashcard")
def learn_flashcard():
    """단계 2: 플래시카드 퀴즈 (4지선다)"""
    nickname = session.get("nickname")
    if not nickname:
        return jsonify({"error": "로그인 필요"}), 401
    user = get_user(nickname)
    
    word = session.get("current_word")
    if not word:
        return jsonify({"error": "먼저 /api/learn/start를 호출하세요"}), 400
    
    pool = get_word_pool(user)
    correct_obj = next((w for w in pool if w["word"] == word), None)
    if not correct_obj:
        return jsonify({"error": "단어를 찾을 수 없어요"}), 404
    
    others = [w for w in pool if w["word"] != word]
    wrong_options = random.sample(others, min(3, len(others)))
    options = wrong_options + [correct_obj]
    random.shuffle(options)
    
    return jsonify({
        "question": correct_obj["meaning"],
        "options": [{"word": o["word"], "meaning": o["meaning"]} for o in options],
        "word": word,
    })

@app.route("/api/learn/fill")
def learn_fill():
    """단계 3: 문장 빈칸 채우기"""
    nickname = session.get("nickname")
    if not nickname:
        return jsonify({"error": "로그인 필요"}), 401
    
    word = session.get("current_word")
    if not word:
        return jsonify({"error": "먼저 /api/learn/start를 호출하세요"}), 400
    
    sentence_data = SENTENCES.get(word)
    if not sentence_data:
        return jsonify({"error": "문장 데이터 없음"}), 404
    
    return jsonify({
        "sentence": sentence_data["sentence"],
        "translation": sentence_data["translation"],
        "word": word,
        "hint": word[0] + "_" * (len(word) - 1),
    })

@app.route("/api/learn/write")
def learn_write():
    """단계 4: 직접 문장 만들기 (AI 채점)"""
    nickname = session.get("nickname")
    if not nickname:
        return jsonify({"error": "로그인 필요"}), 401
    word = session.get("current_word")
    if not word:
        return jsonify({"error": "먼저 /api/learn/start를 호출하세요"}), 400
    
    pool = get_word_pool(get_user(nickname))
    word_obj = next((w for w in pool if w["word"] == word), None)
    
    return jsonify({
        "word": word,
        "meaning": word_obj["meaning"] if word_obj else "",
        "prompt": f"'{word}'을 사용해서 짧은 영어 문장을 만들어봐!",
    })

@app.route("/api/answer", methods=["POST"])
def check_answer():
    """단계별 정답 처리 + 식물 성장/시들기"""
    nickname = session.get("nickname")
    if not nickname:
        return jsonify({"error": "로그인 필요"}), 401
    
    data = request.get_json()
    stage_type = data.get("stage_type")   # 'flashcard', 'fill', 'write'
    selected = data.get("answer", "").strip().lower()
    word = session.get("current_word", "")
    
    user = get_user(nickname)
    plants = user.setdefault("word_plants", {})
    
    is_correct = False
    
    if stage_type == "flashcard":
        is_correct = selected == word.lower()
    elif stage_type == "fill":
        is_correct = selected == word.lower()
    elif stage_type == "write":
        # 간단 체크: 단어가 문장에 포함되어 있으면 통과
        is_correct = word.lower() in selected
    
    plant_data = plants.setdefault(word, {"stage": 0, "wilted": False})
    
    old_stage = plant_data["stage"]
    leveled_up = False
    
    if is_correct:
        user["correct"] += 1
        user["score"] += 10
        
        if plant_data.get("wilted"):
            # 시든 거 복습 성공 → 회복
            plant_data["wilted"] = False
        else:
            # 단계 진행: flashcard=1, fill=2, write=3 → 열매(4)
            stage_map = {"flashcard": 1, "fill": 2, "write": 3}
            required_stage = stage_map.get(stage_type, 1)
            if plant_data["stage"] < required_stage:
                plant_data["stage"] = required_stage
                leveled_up = plant_data["stage"] > old_stage
            # write 완성 시 열매(4)
            if stage_type == "write" and plant_data["stage"] == 3:
                plant_data["stage"] = 4
                leveled_up = True
    else:
        user["wrong"] += 1
        # 틀리면 시들기
        if plant_data["stage"] > 0:
            plant_data["wilted"] = True
    
    plants[word] = plant_data
    user["word_plants"] = plants
    update_user(nickname, user)
    
    return jsonify({
        "correct": is_correct,
        "correct_answer": word,
        "plant": plant_data,
        "leveled_up": leveled_up,
        "user": user,
        "message": get_message(is_correct, leveled_up, plant_data.get("wilted", False), stage_type),
    })

@app.route("/api/review")
def get_review_words():
    """틀린(시든) 단어 목록"""
    nickname = session.get("nickname")
    if not nickname:
        return jsonify({"error": "로그인 필요"}), 401
    user = get_user(nickname)
    pool = get_word_pool(user)
    
    wilted = []
    for w in pool:
        plant = user["word_plants"].get(w["word"])
        if plant and plant.get("wilted"):
            wilted.append({
                "word": w["word"],
                "meaning": w["meaning"],
                "stage": plant["stage"],
            })
    return jsonify(wilted)

@app.route("/api/ranking")
def get_ranking():
    users = load_users()
    ranking = sorted(users.values(), key=lambda x: x["score"], reverse=True)[:10]
    return jsonify([{
        "nickname": u["nickname"],
        "score": u["score"],
        "plants_grown": sum(1 for p in u.get("word_plants", {}).values() if p["stage"] >= 4),
    } for u in ranking])

def get_message(is_correct, leveled_up, wilted, stage_type):
    stage_names = {"flashcard": "플래시카드", "fill": "빈칸 채우기", "write": "문장 만들기"}
    sname = stage_names.get(stage_type, "")
    
    if leveled_up and stage_type == "write":
        return "🍎 열매가 열렸어요! 이 단어 완전히 마스터!"
    if leveled_up:
        msgs = ["🌱 새싹이 돋았어요!", "🌿 잎이 자랐어요!", "🌸 꽃이 피었어요!"]
        return random.choice(msgs)
    if is_correct and wilted is False:
        return f"💧 {sname} 통과! 식물이 기뻐해요!"
    if is_correct:
        return "💚 시든 식물이 회복됐어요!"
    msgs = ["🥀 아쉬워요! 식물이 조금 시들었어요...", "다시 도전해봐요! 💪"]
    return random.choice(msgs)

if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)
    app.run(host='0.0.0.0', port=5000, debug=False)
