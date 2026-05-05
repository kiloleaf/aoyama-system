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
# 🔐 ログイン機能（ここから追加）
# ==========================================
def check_password():
    """パスワードが正しいかチェックする関数"""
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False

    if not st.session_state["password_correct"]:
        st.title("🔐 青山行政書士事務所 システム")
        st.info("このシステムは関係者専用です。パスワードを入力してください。")

        # パスワード入力フォーム
        pwd = st.text_input("パスワード", type="password")
        if st.button("ログイン"):
            if pwd == st.secrets["auth"]["password"]:
                st.session_state["password_correct"] = True
                st.rerun()  # 画面をリロードして中へ進む
            else:
                st.error("❌ パスワードが間違っています。")

        # パスワードが合っていない場合は、ここで画面の描画を強制ストップする！
        st.stop()


# パスワードチェックを実行
check_password()
# ==========================================
# 🔐 ログイン機能（ここまで）
# ==========================================

# ==========================================
# 🚨 写真保存先フォルダ（クラウド対応：Firebase Storageへ移行）
# ==========================================
# ローカルへの保存は廃止し、Firebase Storage を使います
from firebase_admin import storage

# ★ここに、先ほどメモした「バケット名」を入力してください！
os.environ["FIREBASE_STORAGE_BUCKET"] = "aoyama-system-9bc56.firebasestorage.app"


def upload_image_to_storage(image_file, worker_id, file_name="photo.jpg"):
    """画像をFirebase Storageにアップロードし、URLを返す関数"""
    try:
        bucket = storage.bucket(os.environ["FIREBASE_STORAGE_BUCKET"])
        blob = bucket.blob(f"workers/{worker_id}/{file_name}")

        # StreamlitのUploadedFileオブジェクトをバイナリとしてアップロード
        blob.upload_from_file(image_file, content_type=image_file.type)

        # 誰でも画像を見られるように公開URLを生成（有効期限を長めに設定）
        url = blob.generate_signed_url(expiration=timedelta(days=3650), method='GET')
        return url
    except Exception as e:
        st.error(f"画像のアップロードに失敗しました: {e}")
        return None


# ==========================================
# 🔥 Firebase用のデータ取得・変換関数
# ==========================================
# (fetch_all, fetch_where, format_date は今まで通りそのまま)

# ★ get_or_create_worker_dir 関数は不要になったので削除またはコメントアウトしてもOKです
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

# 現在の年を自動取得して「去年・今年・来年・再来年」の4年分の祝日を常にセットする
current_year = datetime.now().year
jp_holidays = holidays.Japan(years=[current_year - 1, current_year, current_year + 1, current_year + 2])


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
            df_tasks = pd.merge(df_tasks, df_workers[['id', 'name_en', 'company_id']], left_on='worker_id',
                                right_on='id', how='left', suffixes=('', '_w'))
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
        df_tasks = df_tasks[(df_tasks['company_id'].isin(valid_company_ids)) | (df_tasks['worker_id'] == '0')]

    # 🌟 ここから画面を「左(カレンダー)7：右(操作パネル)3」に分割します！
    col_cal, col_panel = st.columns([7, 3])

    # ==========================================
    # 🗓️ 左側：カレンダー表示エリア
    # ==========================================
    with col_cal:
        t_date = st.date_input("月を選択", datetime.now(), key="cal_month_view")
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

    # ==========================================
    # 📱 右側：操作パネルエリア
    # ==========================================
    with col_panel:
        st.markdown("### 🛠️ 日別操作パネル")
        st.info("🎯 操作したい日付を選んでください")
        # デフォルトで左のカレンダーと同じ日付が選ばれます
        target_date = st.date_input("操作する日付", t_date, key="panel_target_date")
        target_str = target_date.strftime("%Y-%m-%d")

        st.divider()

        # --- 1. 選んだ日の予定と操作 ---
        st.markdown(f"**【{target_str} の予定】**")
        has_plan = False

        if not df_tasks.empty:
            day_tasks = df_tasks[df_tasks['event_date'] == target_str]
            for _, t in day_tasks.iterrows():
                has_plan = True
                is_done = t['status'] == '完了'
                icon = "☑" if is_done else "▢"
                st.markdown(f"**{icon} {str(t['name_en'])[:4]}**: {t['task_name']}")

                c1, c2 = st.columns(2)
                if c1.button("完了/取消", key=f"tg_{t['id']}", use_container_width=True):
                    new_status = "未完了" if is_done else "完了"
                    db.collection('events_logs').document(t['id']).update({"status": new_status})
                    st.rerun()
                if c2.button("🗑️ 削除", key=f"del_{t['id']}", use_container_width=True):
                    db.collection('events_logs').document(t['id']).delete()
                    st.rerun()
                st.write("---")

        if not df_mileage.empty and 'record_date' in df_mileage.columns:
            day_mileage = df_mileage[df_mileage['record_date'] == target_str]
            for _, m_row in day_mileage.iterrows():
                has_plan = True
                st.markdown(f"**🚗 走行**: {m_row.get('driven_km', 0)}km ({m_row.get('driver_name', '')})")
                if st.button("🗑️ 削除", key=f"del_m_{m_row['id']}"):
                    db.collection('mileage_logs').document(m_row['id']).delete()
                    st.rerun()
                st.write("---")

        if not has_plan:
            st.caption("予定はありません")

        st.divider()

        # --- 2. 新規追加メニュー（アコーディオン） ---
        st.markdown("**➕ 新規追加**")

        with st.expander("👤 外国人材タスクを追加"):
            df_w = fetch_all("foreign_workers")
            df_c = fetch_all("companies")
            if not df_w.empty and not df_c.empty:
                df_w = df_w[df_w['company_id'].isin(valid_company_ids)]
                df_w = pd.merge(df_w, df_c[['id', 'company_name']], left_on='company_id', right_on='id', how='left')
                if not df_w.empty:
                    s_c = st.selectbox("会社", sorted(df_w['company_name'].dropna().unique()), key="add_w_c")
                    df_sub = df_w[df_w['company_name'] == s_c]
                    s_w = st.selectbox("対象者", df_sub['id_x'].tolist(),
                                       format_func=lambda x: df_sub[df_sub['id_x'] == x]['name_en'].values[0],
                                       key="add_w_w")

                    mode = st.radio("追加方法", ["単発", "テンプレート"], horizontal=True, key="add_w_m")
                    if mode == "単発":
                        tn = st.text_input("タスク名", key="add_w_t")
                        if st.button("追加", key="btn_add_w"):
                            db.collection('events_logs').add(
                                {"worker_id": str(s_w), "task_name": tn, "event_date": target_str, "status": "未完了",
                                 "created_at": firestore.SERVER_TIMESTAMP})
                            db.collection('worker_logs').add(
                                {"worker_id": str(s_w), "log_date": target_str, "log_content": f"【タスク登録】{tn}",
                                 "created_at": firestore.SERVER_TIMESTAMP})
                            st.rerun()
                    else:
                        t_df = fetch_all("task_templates")
                        if not t_df.empty:
                            tid = st.selectbox("テンプレート", t_df['id'].tolist(),
                                               format_func=lambda x: t_df[t_df['id'] == x]['template_name'].values[0],
                                               key="add_w_tpl")
                            if st.button("一括追加", key="btn_add_w_tpl"):
                                d_df = fetch_where("template_details", "template_id", "==", tid)
                                for _, d in d_df.iterrows():
                                    evd = (target_date + timedelta(days=int(d['offset_days']))).strftime("%Y-%m-%d")
                                    db.collection('events_logs').add(
                                        {"worker_id": str(s_w), "task_name": d['task_name'], "event_date": evd,
                                         "status": "未完了", "created_at": firestore.SERVER_TIMESTAMP})
                                    db.collection('worker_logs').add({"worker_id": str(s_w), "log_date": evd,
                                                                      "log_content": f"【タスク登録】{d['task_name']}",
                                                                      "created_at": firestore.SERVER_TIMESTAMP})
                                st.rerun()
                        else:
                            st.warning("テンプレートなし")

        with st.expander("🏢 一般・会社タスクを追加"):
            df_c = fetch_all("companies")
            if not df_c.empty:
                df_c = df_c[df_c['id'].isin(valid_company_ids)]
                c_opts = ['0'] + df_c['id'].tolist()
                c_names = ["指定なし（一般業務）"] + df_c['company_name'].tolist()
                s_c_gen = st.selectbox("対象の会社", c_opts, format_func=lambda x: c_names[c_opts.index(x)], key="add_g_c")
                tn_gen = st.text_input("タスク名", key="add_g_t")
                if st.button("追加", key="btn_add_g"):
                    t_name = f"[{c_names[c_opts.index(s_c_gen)]}] {tn_gen}" if s_c_gen != '0' else tn_gen
                    db.collection('events_logs').add(
                        {"worker_id": "0", "company_id": None if s_c_gen == '0' else str(s_c_gen), "task_name": t_name,
                         "event_date": target_str, "status": "未完了", "created_at": firestore.SERVER_TIMESTAMP})
                    if s_c_gen != '0':
                        db.collection('company_logs').add(
                            {"company_id": str(s_c_gen), "log_date": target_str, "log_content": f"【タスク登録】{tn_gen}",
                             "created_at": firestore.SERVER_TIMESTAMP})
                    st.rerun()

        with st.expander("🚗 走行距離を記録"):
            dr_direct = st.selectbox("運転者", ["青山（妻）", "青山（夫）", "スタッフ"], key="add_m_dr")
            dist = st.number_input("距離 (km)", value=0, min_value=0, step=1, key="add_m_d")
            if st.button("記録する", key="btn_add_m"):
                if dist > 0:
                    last_end_km = 0
                    if not df_mileage.empty and 'end_km' in df_mileage.columns:
                        try:
                            last_record = df_mileage.sort_values(by="record_date", ascending=False).iloc[0]
                            last_end_km = int(last_record.get('end_km', 0))
                        except:
                            pass
                    db.collection('mileage_logs').add(
                        {"record_date": target_str, "driver_name": dr_direct, "start_km": last_end_km,
                         "end_km": last_end_km + dist, "driven_km": dist})
                    st.rerun()
                else:
                    st.warning("距離を入力してください")


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
                                    photo_val = str(w.get('photo_path', '')) if pd.notna(w.get('photo_path', '')) else ""
                                    if photo_val and photo_val.startswith('http'):
                                        st.image(photo_val, use_container_width=True)
                                    else:
                                        st.info("📷 写真未登録（または旧データ）")

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

    st.subheader(f"👤 {w['name_en']} さんの情報編集")

    col_img, col_form = st.columns([1, 3])

    with col_img:
        st.write("📷 **写真のアップロード**")
        st.write("※自動で証明写真(3:4)サイズに切り抜かれます。")

        if "uploader_key" not in st.session_state: st.session_state.uploader_key = str(time.time())
        new_photo = st.file_uploader("新しい写真を選択", type=["jpg", "png", "jpeg"], key=st.session_state.uploader_key)

        if new_photo is not None:
            if st.button("🚀 写真をクラウドに保存", type="primary"):
                try:
                    import io
                    # 画像のトリミング処理
                    img = Image.open(new_photo)
                    img = ImageOps.exif_transpose(img)
                    target_size = (600, 800)
                    img_cropped = ImageOps.fit(img, target_size, method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))
                    if img_cropped.mode in ("RGBA", "P"): img_cropped = img_cropped.convert("RGB")

                    # メモリ上で保存（パソコンにファイルを作らない）
                    img_byte_arr = io.BytesIO()
                    img_cropped.save(img_byte_arr, format='JPEG', quality=85)
                    img_byte_arr.seek(0)

                    # ファイルタイプをセットしたダミーオブジェクトを作成
                    class DummyFile:
                        def __init__(self, f): self.f = f; self.type = "image/jpeg"

                        def read(self, *args): return self.f.read(*args)

                        def tell(self): return self.f.tell()

                        def seek(self, *args): return self.f.seek(*args)

                    dummy_photo = DummyFile(img_byte_arr)

                    # Firebase Storageへアップロード！
                    with st.spinner('クラウドへアップロード中...'):
                        image_url = upload_image_to_storage(dummy_photo, target_worker_id)

                    if image_url:
                        # Firestoreの「photo_path」を、新しいURLで上書き
                        db.collection('foreign_workers').document(target_worker_id).update({"photo_path": image_url})
                        st.success(f"✅ 写真を保存しました！");
                        time.sleep(1.0)
                        st.session_state.uploader_key = str(time.time());
                        st.rerun()
                except Exception as e:
                    st.error(f"エラー: {e}")

        st.write("---")
        st.write("**現在の登録写真**")
        # 最新情報を再取得
        doc_ref = db.collection("foreign_workers").document(target_worker_id).get()
        current_data = doc_ref.to_dict() if doc_ref.exists else {}

        photo_val = str(current_data.get('photo_path', ''))
        # photo_pathがURL（httpから始まる）かどうかをチェックして表示
        if photo_val and photo_val.startswith('http'):
            st.image(photo_val, use_container_width=True)
        else:
            st.info("写真未登録（または旧データ）")

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

    # エラーを防ぐため、変数名を新しく安全なもの（m_start, m_end）に変更します
    if 'm_start' not in st.session_state: st.session_state.m_start = last_end_km
    if 'm_end' not in st.session_state: st.session_state.m_end = last_end_km

    t1, t2 = st.tabs(["🔢 メーターで入力", "📏 走行距離(km)を直接入力"])

    with t1:
        with st.container():
            d_meter = st.date_input("日付", datetime.now(), key="date_meter")
            dr_meter = st.selectbox("運転者", ["青山（妻）", "青山（夫）", "スタッフ"], key="driver_meter")

            col1, col2 = st.columns(2)
            with col1:
                # ★ keyの紐付けを外し、純粋な初期値（value）としてだけ渡すように修正
                s_meter = st.number_input("出発時メーター (km)", value=int(st.session_state.m_start), step=1)
            with col2:
                e_meter = st.number_input("帰宅時メーター (km)", value=int(st.session_state.m_end), step=1)

            driven = e_meter - s_meter
            st.info(f"今回の走行距離: **{driven} km**")

            if st.button("💾 メーター記録を保存", type="primary"):
                if driven < 0:
                    st.error("エラー: 帰宅時のメーターが出発時より少なくなっています。")
                else:
                    db.collection('mileage_logs').add(
                        {"record_date": d_meter.strftime("%Y-%m-%d"), "driver_name": dr_meter, "start_km": s_meter,
                         "end_km": e_meter, "driven_km": driven})
                    # 保存後に次の初期値を更新
                    st.session_state.m_start = e_meter
                    st.session_state.m_end = e_meter
                    st.success("メーター記録を保存しました！")
                    time.sleep(1)
                    st.rerun()

    with t2:
        with st.container():
            d_direct = st.date_input("日付", datetime.now(), key="date_direct")
            dr_direct = st.selectbox("運転者", ["青山（妻）", "青山（夫）", "スタッフ"], key="driver_direct")
            dist = st.number_input("走行した距離 (km)", value=0, min_value=0, step=1)

            if st.button("💾 距離だけを記録", type="primary"):
                if dist > 0:
                    new_end = last_end_km + dist
                    db.collection('mileage_logs').add(
                        {"record_date": d_direct.strftime("%Y-%m-%d"), "driver_name": dr_direct,
                         "start_km": last_end_km, "end_km": new_end, "driven_km": dist})
                    # 保存後に次の初期値を更新
                    st.session_state.m_start = new_end
                    st.session_state.m_end = new_end
                    st.success("走行距離を保存しました！")
                    time.sleep(1)
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