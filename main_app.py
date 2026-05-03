import streamlit as st
import pandas as pd
import holidays
import os
import time
import shutil
from datetime import datetime, timedelta
import calendar
from PIL import Image, ImageOps

# ==========================================
# 🔥 Firebase設定（クラウド＆ローカル両対応版）
# ==========================================
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore

# Firebaseの初期化（まだされていない場合のみ）
if not firebase_admin._apps:
    # ☁️ クラウド（Streamlit）で動いているかチェック
    if "firebase" in st.secrets:
        # クラウドの安全な金庫（Secrets）から鍵を取り出す
        cred_dict = dict(st.secrets["firebase"])
        cred = credentials.Certificate(cred_dict)
    else:
        # 💻 ローカル（パソコン）で動いている場合は同じフォルダのJSONを使う
        KEY_PATH = "firebase-key.json"
        cred = credentials.Certificate(KEY_PATH)

    firebase_admin.initialize_app(cred)

# データベース接続
db = firestore.client()

st.set_page_config(page_title="外国人材業務管理システム", layout="wide")

# ==========================================
# 🚨 写真保存先フォルダ（クラウド対応）
# ==========================================
# Cドライブ直指定をやめ、「このプログラムがある場所」を基準にする
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

ASSETS_DIR = os.path.join(BASE_DIR, 'assets')
WORKERS_DIR = os.path.join(ASSETS_DIR, 'workers')
COMPANIES_DIR = os.path.join(ASSETS_DIR, 'companies')

os.makedirs(WORKERS_DIR, exist_ok=True)
os.makedirs(COMPANIES_DIR, exist_ok=True)
# ==========================================

st.markdown("""
    <style>
    .cal-cell { height: 140px; overflow-y: auto; border: 1px solid #555555; padding: 5px; background-color: #2b2b2b; border-radius: 4px; color: #ffffff; }
    .cal-day-header { font-weight: bold; border-bottom: 1px solid #444444; margin-bottom: 5px; padding-bottom: 2px; font-size: 0.9em; }
    .task-item { font-size: 0.8em; margin-bottom: 3px; padding: 3px 5px; background-color: #404040; border-radius: 3px; line-height: 1.2; word-break: break-all; }
    .task-done { color: #aaaaaa; text-decoration: line-through; }
    .task-general { border-left: 3px solid #ffaa00; }
    .task-mileage { border-left: 3px solid #4CAF50; color: #a5d6a7 !important; background-color: #2e3b32; }
    div[data-testid="stExpander"] { border: 1px solid #d1d5db; }
    [data-testid="stFileUploadDropzone"] small { display: none !important; }
    </style>
    """, unsafe_allow_html=True)

jp_holidays = holidays.Japan(years=[2024, 2025, 2026])


# ==========================================
# 🔥 Firebase用のデータ取得・変換関数
# ==========================================
def fetch_all(collection_name):
    docs = db.collection(collection_name).stream()
    data = []
    for doc in docs:
        d = doc.to_dict()
        d['id'] = doc.id  # FirestoreのドキュメントIDを保存
        data.append(d)
    return pd.DataFrame(data)


def fetch_where(collection_name, field, op, value):
    docs = db.collection(collection_name).where(field, op, value).stream()
    data = []
    for doc in docs:
        d = doc.to_dict()
        d['id'] = doc.id
        data.append(d)
    return pd.DataFrame(data)


def format_date(d):
    return "ー" if pd.isna(d) or str(d).strip() in ["None", "", "nan", "1900-01-01"] else d


def get_or_create_worker_dir(worker_id, worker_name_en):
    safe_w_name = "".join([c if c.isalnum() or c in " _-" else "_" for c in str(worker_name_en)])
    worker_dir_name = f"{worker_id}_{safe_w_name}"
    target_dir = os.path.join(WORKERS_DIR, worker_dir_name)
    os.makedirs(target_dir, exist_ok=True)
    return target_dir


st.sidebar.title("📂 管理メニュー")
page = st.sidebar.radio("画面切り替え",
                        ["🏠 ダッシュボード", "🗓️ カレンダー", "👥 外国人材名簿", "📝 名簿編集", "📝 ログ", "➕ 名簿へ新規追加", "⚙️ テンプレート設定",
                         "🚗 走行距離入力"])

st.sidebar.divider()
st.sidebar.subheader("📍 地域フィルター")

# Firebaseから会社リストを取得してフィルター作成
df_comp_all = fetch_all("companies")
area_options = []
if not df_comp_all.empty and 'area' in df_comp_all.columns:
    area_options = sorted(df_comp_all['area'].dropna().unique().tolist())

selected_areas = st.sidebar.multiselect("表示する地域を選択", options=area_options,
                                        default=["近畿"] if "近畿" in area_options else area_options[:1])

# 選択された地域の会社IDリストを作成
valid_company_ids = []
if selected_areas and not df_comp_all.empty:
    valid_company_ids = df_comp_all[df_comp_all['area'].isin(selected_areas)]['id'].tolist()


def show_dashboard():
    st.title("🏠 総合ダッシュボード")
    today = datetime.now().date()
    limit = today + timedelta(days=150)

    col1, col2 = st.columns([6, 4])
    with col1:
        st.subheader("📋 タスク一覧（会社・対象者ごと）")

        # タスク、人材、会社をそれぞれ取得して結合
        df_tasks = fetch_all("events_logs")
        df_workers = fetch_all("foreign_workers")
        df_companies = fetch_all("companies")

        if not df_tasks.empty:
            # 結合用のデータ整理
            if not df_workers.empty:
                df_tasks = pd.merge(df_tasks, df_workers[['id', 'name_en', 'company_id']], left_on='worker_id',
                                    right_on='id', how='left', suffixes=('', '_w'))
            else:
                df_tasks['name_en'] = '一般'
                df_tasks['company_id'] = None

            if not df_companies.empty:
                df_tasks = pd.merge(df_tasks, df_companies[['id', 'company_name']], left_on='company_id', right_on='id',
                                    how='left', suffixes=('', '_c'))
            else:
                df_tasks['company_name'] = '🏢 【一般業務】'

            # Noneの補完
            df_tasks['name_en'] = df_tasks['name_en'].fillna('共通タスク')
            df_tasks['company_name'] = df_tasks['company_name'].fillna('🏢 【一般業務】')
            df_tasks['status'] = df_tasks.get('status', '未完了')

            # 地域フィルタリング (一般業務 worker_id='0' または有効な会社)
            df_tasks = df_tasks[(df_tasks['company_id'].isin(valid_company_ids)) | (df_tasks['worker_id'] == '0')]

            # ソート
            if not df_tasks.empty:
                df_tasks = df_tasks.sort_values(by='event_date')
                grouped = df_tasks.groupby(['company_name', 'name_en'])
                for (comp, name), group in grouped:
                    with st.container():
                        st.markdown(f"**{comp} / 👤 {name}**")
                        for _, r in group.iterrows():
                            c_date, c_task, c_btn = st.columns([2, 5, 2])
                            is_done = r['status'] == '完了'
                            c_date.write(r['event_date'])
                            c_task.markdown(
                                f"{'☑' if is_done else '▢'} {'~~' + r['task_name'] + '~~' if is_done else r['task_name']}")
                            if c_btn.button("☑ 完了取消" if is_done else "▢ 完了にする", key=f"dash_{r['id']}"):
                                new_status = '未完了' if is_done else '完了'
                                db.collection('events_logs').document(r['id']).update({'status': new_status})
                                st.rerun()
                        st.divider()
            else:
                st.write("タスクはありません")
        else:
            st.write("タスクはありません")

    with col2:
        st.subheader("🛂 期限アラート (5ヶ月以内)")
        df_w = fetch_all("foreign_workers")
        df_c = fetch_all("companies")

        alerts = []
        if not df_w.empty and not df_c.empty:
            df_w = df_w[df_w['company_id'].isin(valid_company_ids)]
            df_merged = pd.merge(df_w, df_c[['id', 'company_name']], left_on='company_id', right_on='id', how='left')

            for _, r in df_merged.iterrows():
                p_d, v_d = None, None
                try:
                    p_d = datetime.strptime(str(r.get('passport_expiration_date', '')), '%Y-%m-%d').date()
                except:
                    pass
                try:
                    v_d = datetime.strptime(str(r.get('visa_expiry', '')), '%Y-%m-%d').date()
                except:
                    pass

                if (p_d and today <= p_d <= limit) or (v_d and today <= v_d <= limit):
                    alerts.append({
                        "氏名": r.get('name_en', ''),
                        "企業": r.get('company_name', ''),
                        "書類状況": format_date(r.get('document_status', '')),
                        "パスポート": format_date(r.get('passport_expiration_date', '')),
                        "在留期限": format_date(r.get('visa_expiry', ''))
                    })

        if alerts:
            st.dataframe(pd.DataFrame(alerts), use_container_width=True, hide_index=True)
        else:
            st.write("対象者なし")


def show_calendar():
    st.title("🗓️ カレンダー")

    # データの取得
    df_tasks = fetch_all("events_logs")
    df_workers = fetch_all("foreign_workers")
    df_mileage = fetch_all("mileage_logs")

    # タスクのデータ結合とフィルタリング
    if not df_tasks.empty:
        if not df_workers.empty:
            # ★修正ポイント: suffixesを指定して、タスクの'id'が書き換わらないようにする
            df_tasks = pd.merge(df_tasks, df_workers[['id', 'name_en', 'company_id']], left_on='worker_id',
                                right_on='id', how='left', suffixes=('', '_w'))

            # 個人タスクの場合、company_idがNoneになっているので、worker側のcompany_id(_w)で埋める
            if 'company_id_w' in df_tasks.columns:
                if 'company_id' not in df_tasks.columns:
                    df_tasks['company_id'] = df_tasks['company_id_w']
                else:
                    df_tasks['company_id'] = df_tasks['company_id'].fillna(df_tasks['company_id_w'])
        else:
            df_tasks['name_en'] = '一般'
            df_tasks['company_id'] = None

        df_tasks['name_en'] = df_tasks.get('name_en', pd.Series(dtype=str)).fillna('一般')
        df_tasks['status'] = df_tasks.get('status', '未完了')

        # 地域フィルタリング
        df_tasks = df_tasks[(df_tasks['company_id'].isin(valid_company_ids)) | (df_tasks['worker_id'] == '0')]

    col1, _ = st.columns([2, 5])
    t_date = col1.date_input("月を選択", datetime.now())
    y, m = t_date.year, t_date.month
    cal = calendar.monthcalendar(y, m)

    st.write(f"### {y}年 {m}月")
    cols = st.columns(7)
    for i, d in enumerate(["月", "火", "水", "木", "金", "土", "日"]): cols[i].write(f"**{d}**")

    for week in cal:
        cols = st.columns(7)
        for i, day in enumerate(week):
            with cols[i]:
                if day != 0:
                    d_date = datetime(y, m, day).date()
                    d_str = d_date.strftime("%Y-%m-%d")
                    day_html = f"<div class='cal-day-header' style='color:{'#ff8a8a' if jp_holidays.get(d_date) or i == 6 else '#8ab4ff' if i == 5 else '#ffffff'};'>{day}</div>"
                    tasks_html = ""

                    if not df_tasks.empty:
                        for _, t in df_tasks[df_tasks['event_date'] == d_str].iterrows():
                            base_class = "task-item task-done" if t['status'] == '完了' else "task-item"
                            if str(t['worker_id']) == '0': base_class += " task-general"
                            tasks_html += f"<div class='{base_class}' style='color:#ffffff;'>{'☑' if t['status'] == '完了' else '▢'} {str(t['name_en'])[:4]}: {t['task_name']}</div>"

                    if not df_mileage.empty and 'record_date' in df_mileage.columns:
                        daily_mileage = df_mileage[df_mileage['record_date'] == d_str]
                        for _, m_row in daily_mileage.iterrows():
                            driver = str(m_row.get('driver_name', '')).replace('青山（', '').replace('）', '')
                            tasks_html += f"<div class='task-item task-mileage'>🚗 {m_row.get('driven_km', 0)}km ({driver})</div>"

                    st.markdown(f'<div class="cal-cell">{day_html}{tasks_html}</div>', unsafe_allow_html=True)
                else:
                    st.markdown('<div class="cal-cell" style="background-color:#1e1e1e; border:none;"></div>',
                                unsafe_allow_html=True)

    st.divider()
    st.subheader("🛠️ タスク操作")
    t1, t2 = st.tabs(["➕ 追加", "✏️ 編集・削除"])
    with t1:
        task_type = st.radio("タスク種別", ["👤 外国人材関連", "🏢 会社関連・一般業務"], horizontal=True)
        if task_type == "👤 外国人材関連":
            df_w = fetch_all("foreign_workers")
            df_c = fetch_all("companies")
            if not df_w.empty and not df_c.empty:
                df_w = df_w[df_w['company_id'].isin(valid_company_ids)]
                df_w = pd.merge(df_w, df_c[['id', 'company_name']], left_on='company_id', right_on='id', how='left')

                if not df_w.empty:
                    ca, cb = st.columns(2)
                    s_c = ca.selectbox("会社", sorted(df_w['company_name'].dropna().unique()))
                    df_sub = df_w[df_w['company_name'] == s_c]
                    s_w = cb.selectbox("対象者", df_sub['id_x'].tolist(),
                                       format_func=lambda x: df_sub[df_sub['id_x'] == x]['name_en'].values[0])
                    mode = st.radio("追加方法", ["単発", "テンプレート"], horizontal=True)
                    if mode == "単発":
                        tn = st.text_input("タスク名")
                        td = st.date_input("予定日", datetime.now())
                        if st.button("追加"):
                            db.collection('events_logs').add(
                                {"worker_id": str(s_w), "task_name": tn, "event_date": td.strftime("%Y-%m-%d"),
                                 "status": "未完了", "created_at": firestore.SERVER_TIMESTAMP})
                            db.collection('worker_logs').add(
                                {"worker_id": str(s_w), "log_date": td.strftime("%Y-%m-%d"),
                                 "log_content": f"【タスク登録】{tn}", "created_at": firestore.SERVER_TIMESTAMP})
                            st.rerun()
                    else:
                        t_df = fetch_all("task_templates")
                        if not t_df.empty:
                            tid = st.selectbox("テンプレート", t_df['id'].tolist(),
                                               format_func=lambda x: t_df[t_df['id'] == x]['template_name'].values[0])
                            bd = st.date_input("基準日", datetime.now())
                            if st.button("一括追加"):
                                d_df = fetch_where("template_details", "template_id", "==", tid)
                                for _, d in d_df.iterrows():
                                    evd = (bd + timedelta(days=int(d['offset_days']))).strftime("%Y-%m-%d")
                                    db.collection('events_logs').add(
                                        {"worker_id": str(s_w), "task_name": d['task_name'], "event_date": evd,
                                         "status": "未完了", "created_at": firestore.SERVER_TIMESTAMP})
                                    db.collection('worker_logs').add({"worker_id": str(s_w), "log_date": evd,
                                                                      "log_content": f"【タスク登録】{d['task_name']}",
                                                                      "created_at": firestore.SERVER_TIMESTAMP})
                                st.rerun()
                        else:
                            st.warning("テンプレートがありません")
        else:
            df_c = fetch_all("companies")
            if not df_c.empty:
                df_c = df_c[df_c['id'].isin(valid_company_ids)]
                c_opts = ['0'] + df_c['id'].tolist()
                c_names = ["指定なし（一般業務）"] + df_c['company_name'].tolist()
                s_c = st.selectbox("対象の会社（指定なしでもOK）", c_opts, format_func=lambda x: c_names[c_opts.index(x)])
                tn_gen = st.text_input("タスク名（例：全体会議、社用車点検など）")
                td_gen = st.date_input("予定日", datetime.now())
                if st.button("一般業務・会社タスクを追加"):
                    t_name = f"[{c_names[c_opts.index(s_c)]}] {tn_gen}" if s_c != '0' else tn_gen
                    db.collection('events_logs').add(
                        {"worker_id": "0", "company_id": None if s_c == '0' else str(s_c), "task_name": t_name,
                         "event_date": td_gen.strftime("%Y-%m-%d"), "status": "未完了",
                         "created_at": firestore.SERVER_TIMESTAMP})
                    if s_c != '0':
                        db.collection('company_logs').add(
                            {"company_id": str(s_c), "log_date": td_gen.strftime("%Y-%m-%d"),
                             "log_content": f"【タスク登録】{tn_gen}", "created_at": firestore.SERVER_TIMESTAMP})
                    st.rerun()

    with t2:
        if not df_tasks.empty:
            edf = df_tasks.sort_values("event_date", ascending=False).head(40)

            # ★修正ポイント：idを使ってセレクトボックスを作成（KeyError対策済）
            s_r = st.selectbox(
                "修正するタスク",
                edf['id'].tolist(),
                format_func=lambda
                    x: f"[{edf[edf['id'] == x]['status'].values[0]}] {edf[edf['id'] == x]['event_date'].values[0]} | {edf[edf['id'] == x]['name_en'].values[0]} | {edf[edf['id'] == x]['task_name'].values[0]}"
            )

            t_d = edf[edf['id'] == s_r].iloc[0]
            ce1, ce2, ce3 = st.columns([3, 2, 2])
            en = ce1.text_input("タスク名修正", t_d['task_name'])
            ed = ce2.date_input("日付修正", datetime.strptime(t_d['event_date'], '%Y-%m-%d'))
            es = ce3.selectbox("状態", ["未完了", "完了"], index=0 if t_d.get('status', '未完了') == '未完了' else 1)
            c_btn1, c_btn2 = st.columns([1, 1])
            if c_btn1.button("💾 保存", use_container_width=True):
                db.collection('events_logs').document(s_r).update(
                    {"task_name": en, "event_date": ed.strftime("%Y-%m-%d"), "status": es})
                st.rerun()
            if c_btn2.button("🗑️ 削除", use_container_width=True):
                db.collection('events_logs').document(s_r).delete()
                st.rerun()


def show_worker_list():
    st.title("👥 外国人材名簿")
    search_query = st.text_input("🔍 人材の名前 または 会社名 で検索（大文字・小文字区別なし）", "")

    df_w = fetch_all("foreign_workers")
    df_c = fetch_all("companies")

    if not df_w.empty and not df_c.empty:
        df_w = df_w[df_w['company_id'].isin(valid_company_ids)]
        df = pd.merge(df_w, df_c[['id', 'company_name', 'address']], left_on='company_id', right_on='id', how='left')
        df = df.rename(columns={'address': 'comp_address', 'id_x': 'id'})

        # ソート処理 (Pandasで代用)
        visa_order = {'技能実習1号': 1, '技能実習2号': 2, '技能実習3号': 3, '特定活動': 4, '特定技能1号': 5, '特定技能2号': 6}
        df['visa_order'] = df['visa_status'].map(visa_order).fillna(7)
        df['entry_date'] = pd.to_datetime(df['entry_date'], errors='coerce')
        df = df.sort_values(by=['company_name', 'visa_order', 'entry_date'], ascending=[True, True, True])
        df['entry_date'] = df['entry_date'].dt.strftime('%Y-%m-%d').fillna("ー")

        if search_query:
            mask_name = df['name_en'].str.contains(search_query, case=False, na=False)
            mask_comp = df['company_name'].str.contains(search_query, case=False, na=False)
            df = df[mask_name | mask_comp]

        if not df.empty:
            for comp in df['company_name'].unique():
                is_expanded = True if search_query else False
                with st.expander(f"🏢 {comp} （クリックで展開）", expanded=is_expanded):
                    cdf = df[df['company_name'] == comp]
                    for _, w in cdf.iterrows():
                        with st.expander(
                                f"👤 {w['name_en']} 【{w['visa_status']}】 / 入国日: {format_date(w['entry_date'])}"):
                            tab_info, tab_log = st.tabs(["📋 基本情報", "📝 この人のログ・履歴"])

                            with tab_info:
                                col_img, col_info1, col_info2 = st.columns([2, 4, 4])
                                with col_img:
                                    photo_val = str(w.get('photo_path', '')) if pd.notna(
                                        w.get('photo_path', '')) else ""
                                    if photo_val and photo_val.strip() not in ["None", "nan", ""]:
                                        safe_path = photo_val.replace("/", os.sep).replace("\\", os.sep)
                                        abs_photo_path = os.path.join(BASE_DIR, safe_path)
                                        if os.path.exists(abs_photo_path):
                                            try:
                                                st.image(Image.open(abs_photo_path), use_container_width=True)
                                            except:
                                                st.warning("画像の読込失敗")
                                        else:
                                            st.warning("⚠️ ファイルなし")
                                    else:
                                        st.info("📷 写真未登録")

                                with col_info1:
                                    st.write(f"**生年月日**: {format_date(w.get('birthdate'))}")
                                    st.write(f"**性別**: {format_date(w.get('gender'))}")
                                    st.write(f"**国籍**: {format_date(w.get('nationality'))}")
                                    st.write(f"**出身地**: {format_date(w.get('birthplace'))}")
                                    st.write(f"**本国居住地**: {format_date(w.get('home_address'))}")
                                    st.write(f"**パスポート**: {format_date(w.get('passport_expiration_date'))}")

                                with col_info2:
                                    st.write(f"**🏠 宿舎・寮住所**: {format_date(w.get('residence_address'))}")
                                    st.write(f"**入国日**: {format_date(w.get('entry_date'))}")
                                    st.write(f"**帰国日**: {format_date(w.get('return_date'))}")
                                    st.write(f"**在留期限**: {format_date(w.get('visa_expiry'))}")
                                    st.write(f"**斡旋機関名称**: {format_date(w.get('dispatch_agency'))}")
                                    st.write(f"**会社住所**: {format_date(w.get('comp_address'))}")
                                    st.write(f"**書類状況**: {format_date(w.get('document_status'))}")
                                    st.write(f"**備考**: {format_date(w.get('remarks'))}")

                            with tab_log:
                                w_id = str(w['id'])
                                log_df = fetch_where("worker_logs", "worker_id", "==", w_id)
                                if not log_df.empty:
                                    log_df = log_df.sort_values(by="log_date", ascending=False)

                                with st.form(f"log_form_{w_id}"):
                                    c_d, c_t = st.columns([1, 3])
                                    l_date = c_d.date_input("日付", datetime.now(), key=f"d_{w_id}")
                                    l_text = c_t.text_input("ログ内容（トラブル、ビザ変更、出来事など）", key=f"t_{w_id}")
                                    if st.form_submit_button("＋ ログを追加"):
                                        db.collection('worker_logs').add(
                                            {"worker_id": w_id, "log_date": l_date.strftime("%Y-%m-%d"),
                                             "log_content": l_text, "created_at": firestore.SERVER_TIMESTAMP})
                                        st.success("追加しました！");
                                        st.rerun()

                                if not log_df.empty:
                                    for _, l in log_df.iterrows():
                                        st.markdown(f"**{l['log_date']}**： {l.get('log_content', '')}")
                                        st.divider()
                                else:
                                    st.info("まだログはありません。")
        else:
            st.info("一致するデータがありません")
    else:
        st.info("データがありません")


def show_logs_manager():
    st.title("📝 ログ")
    t1, t2 = st.tabs(["🏢 会社ログ（全体会議・訪問など）", "👤 個人ログ（トラブル・面談など）"])

    with t1:
        df_c = fetch_all("companies")
        if not df_c.empty:
            df_c = df_c[df_c['id'].isin(valid_company_ids)]
            s_c = st.selectbox("会社を選択", df_c['id'].tolist(),
                               format_func=lambda x: df_c[df_c['id'] == x]['company_name'].values[0])

            with st.form("comp_log"):
                l_d = st.date_input("日付", datetime.now())
                l_t = st.text_input("記録内容")
                if st.form_submit_button("会社ログを追加"):
                    db.collection('company_logs').add(
                        {"company_id": str(s_c), "log_date": l_d.strftime("%Y-%m-%d"), "log_content": l_t,
                         "created_at": firestore.SERVER_TIMESTAMP})
                    st.success("追加しました！");
                    st.rerun()

            c_logs = fetch_where("company_logs", "company_id", "==", str(s_c))
            if not c_logs.empty:
                c_logs = c_logs.sort_values(by="log_date", ascending=False)
                for _, l in c_logs.iterrows():
                    st.markdown(f"**{l['log_date']}**： {l.get('log_content', '')}")
                    st.divider()
            else:
                st.write("記録なし")

    with t2:
        df_w = fetch_all("foreign_workers")
        df_c = fetch_all("companies")
        if not df_w.empty and not df_c.empty:
            df_w = df_w[df_w['company_id'].isin(valid_company_ids)]
            df_w = pd.merge(df_w, df_c[['id', 'company_name']], left_on='company_id', right_on='id', how='left')
            if not df_w.empty:
                s_w = st.selectbox("対象者を選択", df_w['id_x'].tolist(), format_func=lambda
                    x: f"[{df_w[df_w['id_x'] == x]['company_name'].values[0]}] {df_w[df_w['id_x'] == x]['name_en'].values[0]}")

                w_logs = fetch_where("worker_logs", "worker_id", "==", str(s_w))
                if not w_logs.empty:
                    w_logs = w_logs.sort_values(by="log_date", ascending=False)
                    for _, l in w_logs.iterrows():
                        st.markdown(f"**{l['log_date']}**： {l.get('log_content', '')}")
                        st.divider()
                else:
                    st.write("記録なし")


def show_data_editor():
    st.title("📝 名簿編集")
    df_cf = fetch_all("companies")

    if df_cf.empty: st.warning("対象地域に会社なし"); return
    df_cf_filtered = df_cf[df_cf['id'].isin(valid_company_ids)]
    if df_cf_filtered.empty: st.warning("対象地域に会社なし"); return

    c1, c2 = st.columns(2)
    with c1:
        sc = st.selectbox("1. 現在の会社", df_cf_filtered['company_name'].tolist())
        scid = df_cf_filtered[df_cf_filtered['company_name'] == sc]['id'].values[0]

    df_w = fetch_where("foreign_workers", "company_id", "==", scid)
    with c2:
        if df_w.empty: st.error("人材なし"); return
        sw = st.selectbox("2. 対象者", df_w['name_en'].tolist())
        w = df_w[df_w['name_en'] == sw].iloc[0]

    target_worker_id = w['id']
    target_dir = get_or_create_worker_dir(target_worker_id, w['name_en'])

    st.subheader(f"👤 {w['name_en']} さんの情報編集")

    current_photo_path = str(w.get('photo_path', ''))
    if current_photo_path and current_photo_path.strip() not in ["None", "nan", ""]:
        old_abs_path = os.path.join(BASE_DIR, current_photo_path.replace("/", os.sep).replace("\\", os.sep))
        new_file_name = "photo.jpg"
        new_abs_path = os.path.join(target_dir, new_file_name)
        new_relative_path = os.path.relpath(new_abs_path, BASE_DIR).replace("\\", "/")

        if "workers" not in current_photo_path and os.path.exists(old_abs_path):
            try:
                shutil.move(old_abs_path, new_abs_path)
                db.collection('foreign_workers').document(target_worker_id).update({"photo_path": new_relative_path})
                st.toast("✅ 過去の写真を新しい個人フォルダに自動で移行しました！")
            except Exception as e:
                st.error(f"写真の移行中にエラー: {e}")

    if st.button("📂 この人の専用フォルダをパソコンで開く"):
        try:
            os.startfile(target_dir)
        except:
            st.warning("ブラウザから直接フォルダを開けない環境です。")
    st.info(f"保存先: {target_dir}")

    col_img, col_form = st.columns([1, 3])

    with col_img:
        st.write("📷 **写真のアップロード**")
        st.write("※自動で証明写真(3:4)サイズに切り抜かれます。")

        if "uploader_key" not in st.session_state: st.session_state.uploader_key = str(time.time())
        new_photo = st.file_uploader("新しい写真を選択", type=["jpg", "png", "jpeg"], key=st.session_state.uploader_key)

        if new_photo is not None:
            if st.button("🚀 写真を登録", type="primary"):
                try:
                    img = Image.open(new_photo)
                    img = ImageOps.exif_transpose(img)
                    target_size = (600, 800)
                    img_cropped = ImageOps.fit(img, target_size, method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))
                    if img_cropped.mode in ("RGBA", "P"): img_cropped = img_cropped.convert("RGB")

                    file_name = "photo.jpg"
                    abs_save_path = os.path.join(target_dir, file_name)
                    relative_path = os.path.relpath(abs_save_path, BASE_DIR).replace("\\", "/")
                    img_cropped.save(abs_save_path, format="JPEG", quality=85)

                    db.collection('foreign_workers').document(target_worker_id).update({"photo_path": relative_path})
                    st.success(f"✅ 写真を保存しました！");
                    time.sleep(1.0)
                    st.session_state.uploader_key = str(time.time());
                    st.rerun()
                except Exception as e:
                    st.error(f"エラー: {e}")

        st.write("---")
        st.write("**現在の登録写真**")
        doc_ref = db.collection("foreign_workers").document(target_worker_id).get()
        current_data = doc_ref.to_dict() if doc_ref.exists else {}

        photo_val = str(current_data.get('photo_path', ''))
        if photo_val and photo_val.strip() not in ["None", "nan", ""]:
            safe_path = photo_val.replace("/", os.sep).replace("\\", os.sep)
            abs_photo_path = os.path.join(BASE_DIR, safe_path)
            if os.path.exists(abs_photo_path):
                try:
                    st.image(Image.open(abs_photo_path), use_container_width=True)
                except:
                    st.warning("画像の読込失敗")
            else:
                st.warning(f"⚠️ 画像ファイルがありません")
        else:
            st.info("写真未登録")

    with col_form:
        with st.form("e"):
            st.write("🏢 **所属・居住地**")
            c_names = df_cf['company_name'].tolist()
            nc = st.selectbox("所属会社（移籍）", c_names, index=c_names.index(sc) if sc in c_names else 0)
            ncid = df_cf[df_cf['company_name'] == nc]['id'].values[0]
            nr = st.text_input("寮の住所", value=format_date(w.get('residence_address', '')))

            st.write("---")
            st.write("👤 **基本情報**")
            cc1, cc2, cc3 = st.columns(3)
            nbirth = cc1.text_input("生年月日（例: 2000/01/01）", value=format_date(w.get('birthdate', '')))
            ngender = cc2.text_input("性別", value=format_date(w.get('gender', '')))
            nnat = cc3.text_input("国籍", value=format_date(w.get('nationality', '')))

            cc4, cc5 = st.columns(2)
            nbirthp = cc4.text_input("出身地", value=format_date(w.get('birthplace', '')))
            nhome = cc5.text_input("本国居住地", value=format_date(w.get('home_address', '')))

            st.write("---")
            st.write("✈️ **入出境・期限管理**")
            ca, cb = st.columns(2)

            def pd_dt(s):
                try:
                    return datetime.strptime(str(s), '%Y-%m-%d')
                except:
                    return datetime.now()

            with ca:
                nv = st.date_input("在留期限", pd_dt(w.get('visa_expiry', '')))
                np = st.date_input("パスポート期限", pd_dt(w.get('passport_expiration_date', '')))
            with cb:
                nentry = st.text_input("入国日（例: 2023/04/01）", value=format_date(w.get('entry_date', '')))
                nret = st.text_input("帰国日", value=format_date(w.get('return_date', '')))

            st.write("---")
            st.write("📝 **その他詳細**")
            cx1, cx2 = st.columns(2)
            nagency = cx1.text_input("斡旋機関名称", value=format_date(w.get('dispatch_agency', '')))
            opts = ["本人保持", "事務所預かり", "更新手続中", "紛失中", ""]
            current_doc = w.get('document_status', '')
            ndoc = cx2.selectbox("書類状況", opts, index=opts.index(current_doc) if current_doc in opts else 0)
            nrem = st.text_area("備考", value=format_date(w.get('remarks', '')))

            if st.form_submit_button("💾 右側の文字情報をすべて保存"):
                update_data = {
                    "company_id": str(ncid), "residence_address": nr, "birthdate": nbirth,
                    "gender": ngender, "nationality": nnat, "birthplace": nbirthp,
                    "home_address": nhome, "visa_expiry": nv.strftime('%Y-%m-%d'),
                    "passport_expiration_date": np.strftime('%Y-%m-%d'), "entry_date": nentry,
                    "return_date": nret, "dispatch_agency": nagency, "document_status": ndoc, "remarks": nrem
                }
                db.collection('foreign_workers').document(target_worker_id).update(update_data)
                st.success("更新完了！");
                st.rerun()


def show_tpl_set():
    st.title("⚙️ テンプレート設定")
    with st.form("t"):
        tn = st.text_input("新規テンプレート名")
        if st.form_submit_button("作成"):
            db.collection('task_templates').add({"template_name": tn, "created_at": firestore.SERVER_TIMESTAMP})
            st.rerun()

    df_t = fetch_all("task_templates")
    if not df_t.empty:
        stn = st.selectbox("編集するテンプレート", df_t['id'].tolist(),
                           format_func=lambda x: df_t[df_t['id'] == x]['template_name'].values[0])
        if st.button("🗑️ テンプレートを削除"):
            db.collection('task_templates').document(stn).delete()
            d_df = fetch_where("template_details", "template_id", "==", stn)
            for d_id in d_df['id']: db.collection('template_details').document(d_id).delete()
            st.rerun()
        st.divider()

        df_d = fetch_where("template_details", "template_id", "==", stn)
        if not df_d.empty:
            df_d['offset_days'] = pd.to_numeric(df_d['offset_days'])
            df_d = df_d.sort_values(by="offset_days")
            st.table(df_d[['task_name', 'offset_days']])

        with st.form("ad"):
            dn = st.text_input("タスク内容")
            do = st.number_input("日数", value=0)
            if st.form_submit_button("追加"):
                db.collection('template_details').add({"template_id": stn, "task_name": dn, "offset_days": do})
                st.rerun()

        if not df_d.empty:
            del_id = st.selectbox("削除する詳細", df_d['id'].tolist(),
                                  format_func=lambda x: df_d[df_d['id'] == x]['task_name'].values[0])
            if st.button("❌ 削除"):
                db.collection('template_details').document(del_id).delete()
                st.rerun()


def show_add_new():
    st.title("➕ 名簿へ新規追加")
    t1, t2 = st.tabs(["🏢 会社の新規登録", "👤 外国人材の新規登録"])
    with t1:
        with st.form("c"):
            cn = st.text_input("会社名")
            ca = st.selectbox("地域", ["近畿", "関東", "東海", "静岡", "九州", "中四国", "北信越", "北海道・東北"])
            if st.form_submit_button("登録"):
                if cn:
                    db.collection('companies').add(
                        {"company_name": cn, "area": ca, "created_at": firestore.SERVER_TIMESTAMP})
                    st.success("登録完了");
                    st.rerun()
    with t2:
        df_c = fetch_all("companies")
        if not df_c.empty:
            df_c = df_c[df_c['id'].isin(valid_company_ids)]
            with st.form("w"):
                comp = st.selectbox("所属会社", df_c['id'].tolist(),
                                    format_func=lambda x: df_c[df_c['id'] == x]['company_name'].values[0])
                name = st.text_input("氏名（ローマ字）")
                visa = st.selectbox("在留資格", ["技能実習1号", "技能実習2号", "技能実習3号", "特定技能1号", "特定技能2号", "特定活動", "その他"])
                if st.form_submit_button("登録"):
                    if name:
                        db.collection('foreign_workers').add({
                            "company_id": str(comp), "name_en": name, "visa_status": visa,
                            "is_away": 0, "document_status": "本人保持", "created_at": firestore.SERVER_TIMESTAMP
                        })
                        st.success("登録完了");
                        st.rerun()
        else:
            st.warning("対象会社なし")


def show_mileage():
    st.title("🚗 走行距離入力")
    df_m = fetch_all("mileage_logs")
    last_end_km = 0
    if not df_m.empty and 'end_km' in df_m.columns:
        try:
            last_record = df_m.sort_values(by="record_date", ascending=False).iloc[0]
            last_end_km = int(last_record.get('end_km', 0))
        except:
            pass

    if 'start_val' not in st.session_state: st.session_state.start_val = last_end_km
    if 'end_val' not in st.session_state: st.session_state.end_val = last_end_km

    def swap_values():
        st.session_state.start_val, st.session_state.end_val = st.session_state.end_val, st.session_state.start_val

    t1, t2 = st.tabs(["🔢 メーターで入力", "📏 走行距離(km)を直接入力"])

    with t1:
        with st.container():
            d_meter = st.date_input("日付", datetime.now(), key="date_meter")
            dr_meter = st.selectbox("運転者", ["青山（妻）", "青山（夫）", "スタッフ"], key="driver_meter")

            col1, col2, col3 = st.columns([4, 1, 4])
            with col1:
                s_meter = st.number_input("出発時メーター (km)", value=int(st.session_state.start_val), key="start_val",
                                          step=1)
            with col2:
                st.write("");
                st.write("")
                st.button("🔄 入替", on_click=swap_values, help="出発と帰宅の数値を入れ替えます")
            with col3:
                e_meter = st.number_input("帰宅時メーター (km)", value=int(st.session_state.end_val), key="end_val", step=1)

            driven = e_meter - s_meter
            st.info(f"今回の走行距離: **{driven} km**")

            if st.button("💾 メーター記録を保存", type="primary"):
                if driven < 0:
                    st.error("エラー: 帰宅時のメーターが出発時より少なくなっています。")
                else:
                    db.collection('mileage_logs').add(
                        {"record_date": d_meter.strftime("%Y-%m-%d"), "driver_name": dr_meter, "start_km": s_meter,
                         "end_km": e_meter, "driven_km": driven})
                    st.session_state.start_val = e_meter
                    st.session_state.end_val = e_meter
                    st.success("メーター記録を保存しました！");
                    time.sleep(1);
                    st.rerun()

    with t2:
        with st.container():
            d_direct = st.date_input("日付", datetime.now(), key="date_direct")
            dr_direct = st.selectbox("運転者", ["青山（妻）", "青山（夫）", "スタッフ"], key="driver_direct")
            dist = st.number_input("走行した距離 (km)", value=0, min_value=0, step=1)

            if st.button("💾 距離だけを記録", type="primary"):
                if dist > 0:
                    db.collection('mileage_logs').add(
                        {"record_date": d_direct.strftime("%Y-%m-%d"), "driver_name": dr_direct,
                         "start_km": last_end_km, "end_km": last_end_km + dist, "driven_km": dist})
                    st.session_state.start_val = last_end_km + dist
                    st.session_state.end_val = last_end_km + dist
                    st.success("走行距離を保存しました！");
                    time.sleep(1);
                    st.rerun()
                else:
                    st.warning("距離を入力してください。")


if page == "🏠 ダッシュボード":
    show_dashboard()
elif page == "🗓️ カレンダー":
    show_calendar()
elif page == "👥 外国人材名簿":
    show_worker_list()
elif page == "📝 名簿編集":
    show_data_editor()
elif page == "📝 ログ":
    show_logs_manager()
elif page == "➕ 名簿へ新規追加":
    show_add_new()
elif page == "⚙️ テンプレート設定":
    show_tpl_set()
elif page == "🚗 走行距離入力":
    show_mileage()