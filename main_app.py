import streamlit as st
import pandas as pd
import holidays
import os
import time
from datetime import datetime, timedelta
import calendar
from PIL import Image, ImageOps

# ==========================================
# 🔥 Firebase設定（クラウド＆ローカル両対応版）
# ==========================================
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
from firebase_admin import storage

if not firebase_admin._apps:
    if "firebase" in st.secrets:
        cred_dict = dict(st.secrets["firebase"])
        cred = credentials.Certificate(cred_dict)
    else:
        KEY_PATH = "firebase-key.json"
        cred = credentials.Certificate(KEY_PATH)

    firebase_admin.initialize_app(cred)

db = firestore.client()
os.environ["FIREBASE_STORAGE_BUCKET"] = "aoyama-system-9bc56.firebasestorage.app"

st.set_page_config(page_title="外国人材業務管理システム", layout="wide")


# ==========================================
# 🔐 ログイン機能
# ==========================================
def check_password():
    if "password_correct" not in st.session_state: st.session_state["password_correct"] = False
    if not st.session_state["password_correct"]:
        st.title("🔐 青山行政書士事務所 システム")
        st.info("このシステムは関係者専用です。パスワードを入力してください。")
        pwd = st.text_input("パスワード", type="password")
        if st.button("ログイン"):
            if pwd == st.secrets["auth"]["password"]:
                st.session_state["password_correct"] = True
                st.rerun()
            else:
                st.error("❌ パスワードが間違っています。")
        st.stop()


check_password()


# ==========================================
# 🚀 爆速化・共通関数（INT64型エラー徹底完全対策）
# ==========================================
@st.cache_data(ttl=300)
def fetch_all_cached(collection_name):
    docs = db.collection(collection_name).stream()
    return pd.DataFrame([{"id": str(doc.id), **doc.to_dict()} for doc in docs])


def clear_caches():
    st.cache_data.clear()


def fetch_all(collection_name):
    docs = db.collection(collection_name).stream()
    return pd.DataFrame([{"id": str(doc.id), **doc.to_dict()} for doc in docs])


def fetch_where(collection_name, field, op, value):
    docs = db.collection(collection_name).where(field, op, value).stream()
    return pd.DataFrame([{"id": str(doc.id), **doc.to_dict()} for doc in docs])


def format_date(d):
    return "ー" if pd.isna(d) or str(d).strip() in ["None", "", "nan", "1900-01-01"] else str(d)


# ==========================================
# 🚨 ファイル管理機能
# ==========================================
def upload_image_to_storage(image_file, worker_id, file_name="photo.jpg"):
    try:
        bucket = storage.bucket(os.environ["FIREBASE_STORAGE_BUCKET"])
        blob = bucket.blob(f"workers/{worker_id}/{file_name}")
        blob.upload_from_file(image_file, content_type=image_file.type)
        return blob.generate_signed_url(expiration=timedelta(days=3650), method='GET')
    except Exception as e:
        st.error(f"エラー: {e}")
        return None


def manage_files_ui(path_prefix, label="ファイル"):
    bucket = storage.bucket(os.environ["FIREBASE_STORAGE_BUCKET"])
    st.write(f"### 📂 {label}保管庫")

    uploaded_file = st.file_uploader(f"{label}をアップロード", type=["pdf", "doc", "docx", "jpg", "png"],
                                     key=f"upload_{path_prefix}")
    if uploaded_file and st.button(f"{label}を保存", key=f"btn_save_{path_prefix}"):
        with st.spinner("アップロード中..."):
            blob = bucket.blob(f"{path_prefix}/{uploaded_file.name}")
            blob.upload_from_file(uploaded_file, content_type=uploaded_file.type)
            st.success("アップロード完了！")
            st.rerun()
    st.write("---")

    blobs = bucket.list_blobs(prefix=path_prefix)
    file_list = [b for b in blobs if b.name.replace(f"{path_prefix}/", "")]

    if not file_list:
        st.info("保存されているファイルはありません。")
    else:
        for b in file_list:
            fname = b.name.replace(f"{path_prefix}/", "")
            col_name, col_dl, col_del = st.columns([5, 2, 1])
            col_name.write(f"📄 {fname}")
            col_dl.markdown(f"[📥 ダウンロード]({b.generate_signed_url(expiration=timedelta(hours=1), method='GET')})")
            if col_del.button("🗑️", key=f"del_{b.name}"):
                b.delete()
                st.rerun()


# ==========================================
# 🎨 UIスタイルと祝日
# ==========================================
st.markdown("""
    <style>
    .cal-cell { height: 140px; overflow-y: auto; border: 1px solid #555555; padding: 5px; background-color: #2b2b2b; border-radius: 4px; color: #ffffff; }
    .cal-day-header { font-weight: bold; border-bottom: 1px solid #444444; margin-bottom: 5px; padding-bottom: 2px; font-size: 0.9em; }
    .task-item { font-size: 0.8em; margin-bottom: 3px; padding: 3px 5px; background-color: #404040; border-radius: 3px; line-height: 1.2; word-break: break-all; }
    .task-done { color: #aaaaaa; text-decoration: line-through; }
    .task-general { border-left: 3px solid #ffaa00; }
    .task-mileage { border-left: 3px solid #4CAF50; color: #a5d6a7 !important; background-color: #2e3b32; }
    </style>
    """, unsafe_allow_html=True)
current_year = datetime.now().year
jp_holidays = holidays.Japan(years=[current_year - 1, current_year, current_year + 1, current_year + 2])

# ==========================================
# 📂 サイドバーと共通フィルター
# ==========================================
st.sidebar.title("📂 管理メニュー")
page = st.sidebar.radio("画面切り替え", [
    "🏠 ダッシュボード", "🗓️ カレンダー", "👥 人材名簿", "🏢 会社情報", "📝 ログ一覧", "➕ 新規登録", "⚙️ テンプレート設定", "🚗 走行距離入力"
])
st.sidebar.divider()
st.sidebar.subheader("📍 地域フィルター")
df_comp_all = fetch_all_cached("companies")
area_options = sorted(
    df_comp_all['area'].dropna().unique().tolist()) if not df_comp_all.empty and 'area' in df_comp_all.columns else []
selected_areas = st.sidebar.multiselect("表示する地域を選択", options=area_options,
                                        default=["近畿"] if "近畿" in area_options else area_options[:1])
valid_company_ids = df_comp_all[df_comp_all['area'].isin(selected_areas)][
    'id'].tolist() if selected_areas and not df_comp_all.empty else []


# ==========================================
# 🏠 画面：ダッシュボード
# ==========================================
def show_dashboard():
    st.title("🏠 総合ダッシュボード")
    today = datetime.now().date()

    start_window = today - timedelta(days=30)
    end_window = today + timedelta(days=30)

    col1, col2 = st.columns([6, 4])
    with col1:
        st.subheader(f"📋 直近のタスク一覧 ({start_window} ～ {end_window})")

        task_filter = st.radio("表示するタスクの種類", ["すべて表示", "帰国手続きのみ", "入管手続きのみ"], horizontal=True)
        st.write("---")

        df_tasks = fetch_all_cached("events_logs")
        df_workers = fetch_all_cached("foreign_workers")

        if not df_tasks.empty:
            if 'category' not in df_tasks.columns:
                df_tasks['category'] = '一般業務'
            else:
                df_tasks['category'] = df_tasks['category'].fillna('一般業務')

            if 'status' not in df_tasks.columns:
                df_tasks['status'] = '未完了'
            else:
                df_tasks['status'] = df_tasks['status'].fillna('未完了')

            if not df_workers.empty:
                df_tasks = pd.merge(df_tasks, df_workers[['id', 'name_en', 'company_id']], left_on='worker_id',
                                    right_on='id', how='left', suffixes=('', '_w'))
            else:
                df_tasks['name_en'] = '一般'
                df_tasks['company_id'] = None

            if not df_comp_all.empty:
                df_tasks = pd.merge(df_tasks, df_comp_all[['id', 'company_name']], left_on='company_id', right_on='id',
                                    how='left', suffixes=('', '_c'))
            else:
                df_tasks['company_name'] = '🏢 【一般業務】'

            if 'name_en' not in df_tasks.columns:
                df_tasks['name_en'] = '共通タスク'
            else:
                df_tasks['name_en'] = df_tasks['name_en'].fillna('共通タスク')

            if 'company_name' not in df_tasks.columns:
                df_tasks['company_name'] = '🏢 【一般業務】'
            else:
                df_tasks['company_name'] = df_tasks['company_name'].fillna('🏢 【一般業務】')

            df_tasks = df_tasks[(df_tasks['company_id'].isin(valid_company_ids)) | (df_tasks['worker_id'] == '0')]

            if not df_tasks.empty:
                df_tasks['event_date_obj'] = pd.to_datetime(df_tasks['event_date']).dt.date
                df_tasks = df_tasks[
                    (df_tasks['event_date_obj'] >= start_window) & (df_tasks['event_date_obj'] <= end_window)]

            if task_filter == "帰国手続きのみ":
                df_tasks = df_tasks[df_tasks['category'] == "帰国手続き"]
            elif task_filter == "入管手続きのみ":
                df_tasks = df_tasks[df_tasks['category'] == "入管手続き"]

            if not df_tasks.empty:
                for (comp, name), group in df_tasks.sort_values(by='event_date').groupby(['company_name', 'name_en']):
                    st.markdown(f"**{comp} / 👤 {name}**")
                    for _, r in group.iterrows():
                        c_date, c_task, c_btn = st.columns([2, 5, 2])
                        is_done = r['status'] == '完了'
                        c_date.write(r['event_date'])

                        cat_badge = ""
                        if r['category'] == "帰国手続き":
                            cat_badge = "<span style='color:#ff4b4b; font-weight:bold;'>【帰国】</span> "
                        elif r['category'] == "入管手続き":
                            cat_badge = "<span style='color:#4bb5ff; font-weight:bold;'>【入管】</span> "

                        task_disp = f"~~{r['task_name']}~~" if is_done else r['task_name']
                        c_task.markdown(f"{'☑' if is_done else '▢'} {cat_badge}{task_disp}", unsafe_allow_html=True)

                        if c_btn.button("☑ 取消" if is_done else "▢ 完了", key=f"dash_{r['id']}"):
                            db.collection('events_logs').document(str(r['id'])).update(
                                {'status': '未完了' if is_done else '完了'})
                            clear_caches();
                            st.rerun()
                    st.divider()
            else:
                st.write("該当するタスクはありません。")
        else:
            st.write("タスクデータがありません。")

    with col2:
        st.subheader("🛂 人材 期限・トラブル防止アラート")
        df_w = fetch_all_cached("foreign_workers")
        w_alerts = []
        if not df_w.empty and not df_comp_all.empty:

            if 'enrollment_status' not in df_w.columns:
                df_w['enrollment_status'] = '在籍中'
            else:
                df_w['enrollment_status'] = df_w['enrollment_status'].fillna('在籍中')

            df_w = df_w[df_w['enrollment_status'] == '在籍中']

            df_merged = pd.merge(df_w[df_w['company_id'].isin(valid_company_ids)], df_comp_all[['id', 'company_name']],
                                 left_on='company_id', right_on='id', how='left')
            limit_5m = today + timedelta(days=150)
            limit_14d = today + timedelta(days=14)

            for _, r in df_merged.iterrows():
                try:
                    p_d = datetime.strptime(str(r.get('passport_expiration_date', '')), '%Y-%m-%d').date()
                    if today <= p_d <= limit_5m: w_alerts.append(
                        {"氏名": r.get('name_en', ''), "種類": "パスポート(5ヶ月以内)", "日付": str(p_d)})
                except:
                    pass

                try:
                    v_d = datetime.strptime(str(r.get('visa_expiry', '')), '%Y-%m-%d').date()
                    if today <= v_d <= limit_5m: w_alerts.append(
                        {"氏名": r.get('name_en', ''), "種類": "在留カード期限(5ヶ月以内)", "日付": str(v_d)})
                except:
                    pass

                try:
                    ret_d = datetime.strptime(str(r.get('return_date', '')), '%Y-%m-%d').date()
                    if today <= ret_d <= limit_14d:
                        doc_stat = str(r.get('document_status', ''))
                        if doc_stat not in ["本人所持", "本人保持"]:
                            w_alerts.append({"氏名": r.get('name_en', ''), "種類": "🚨帰国間近(書類本人未所持)", "日付": str(ret_d)})
                except:
                    pass

        if w_alerts:
            st.dataframe(pd.DataFrame(w_alerts), use_container_width=True, hide_index=True)
        else:
            st.write("対象者なし")

        st.write("---")

        st.subheader("🏢 会社 期限・注意アラート")
        c_alerts = []
        if not df_comp_all.empty:
            for _, c in df_comp_all[df_comp_all['id'].isin(valid_company_ids)].iterrows():
                # 36協定起算日からの1年経過アラート
                a36_start_str = str(c.get('agreement_36_start_date', ''))
                if a36_start_str and a36_start_str not in ["nan", "ー", "None", ""]:
                    try:
                        start_date = datetime.strptime(a36_start_str, '%Y-%m-%d').date()
                        limit_date = start_date + timedelta(days=365)  # 起算日から1年後
                        if today >= limit_date:
                            c_alerts.append({"会社名": c['company_name'], "種類": "36協定 期限切れ", "日付": str(limit_date)})
                    except:
                        pass

                # 技能実習責任者講習日の2.5年（約913日）経過アラート
                sup_tr_str = str(c.get('supervisor_training_date', ''))
                if sup_tr_str and sup_tr_str not in ["nan", "ー", "None", ""]:
                    try:
                        sup_tr_date = datetime.strptime(sup_tr_str, '%Y-%m-%d').date()
                        limit_2_5y = sup_tr_date + timedelta(days=913)  # 2.5年後(約913日)
                        if today >= limit_2_5y:
                            c_alerts.append({"会社名": c['company_name'], "種類": "責任者講習から2.5年経過", "日付": sup_tr_str})
                    except:
                        pass

        if c_alerts:
            st.dataframe(pd.DataFrame(c_alerts), use_container_width=True, hide_index=True)
        else:
            st.write("対象会社なし")


# ==========================================
# 🗓️ 画面：カレンダー
# ==========================================
def show_calendar():
    st.title("🗓️ カレンダー")

    cal_filter = st.radio("表示フィルター", ["すべて表示", "タスクのみ表示", "走行距離のみ表示"], horizontal=True)
    st.divider()

    if 'cal_current_date' not in st.session_state:
        st.session_state.cal_current_date = datetime.now().date()

    df_tasks = fetch_all_cached("events_logs")
    df_workers = fetch_all_cached("foreign_workers")
    df_mileage = fetch_all_cached("mileage_logs")

    if not df_tasks.empty and not df_workers.empty:
        df_tasks = pd.merge(df_tasks, df_workers[['id', 'name_en', 'company_id']], left_on='worker_id', right_on='id',
                            how='left', suffixes=('', '_w'))
        df_tasks['company_id'] = df_tasks.get('company_id_w', df_tasks.get('company_id'))

    if not df_tasks.empty:
        if 'name_en' not in df_tasks.columns:
            df_tasks['name_en'] = '一般'
        else:
            df_tasks['name_en'] = df_tasks['name_en'].fillna('一般')

        if 'status' not in df_tasks.columns:
            df_tasks['status'] = '未完了'
        else:
            df_tasks['status'] = df_tasks['status'].fillna('未完了')

        if 'category' not in df_tasks.columns:
            df_tasks['category'] = '一般業務'
        else:
            df_tasks['category'] = df_tasks['category'].fillna('一般業務')

        df_tasks = df_tasks[(df_tasks['company_id'].isin(valid_company_ids)) | (df_tasks['worker_id'] == '0')]

    col_cal, col_panel = st.columns([7, 3])
    with col_cal:
        if st.button("📅 今日に戻る", type="secondary"):
            st.session_state.cal_current_date = datetime.now().date()
            st.rerun()

        t_date = st.date_input("月を選択", st.session_state.cal_current_date, key="cal_month_view")
        st.session_state.cal_current_date = t_date
        y, m = t_date.year, t_date.month
        calendar.setfirstweekday(calendar.SUNDAY)

        week_cols = st.columns(7)
        for i, d in enumerate(["日", "月", "火", "水", "木", "金", "土"]):
            week_cols[i].write(f"**{d}**")

        for week in calendar.monthcalendar(y, m):
            cols = st.columns(7)
            for i, day in enumerate(week):
                with cols[i]:
                    if day != 0:
                        d_date = datetime(y, m, day).date()
                        d_str = d_date.strftime("%Y-%m-%d")

                        is_today = (d_date == datetime.now().date())
                        bg_style = "background-color: #1c3322; border: 2px solid #2ea44f;" if is_today else ""
                        color = '#ff8a8a' if jp_holidays.get(d_date) or i == 0 else '#8ab4ff' if i == 6 else '#ffffff'
                        html = f"<div class='cal-day-header' style='color:{color};'>{'📍 今日 ' if is_today else ''}{day}</div>"

                        tasks_html = ""
                        if cal_filter in ["すべて表示", "タスクのみ表示"]:
                            if not df_tasks.empty:
                                for _, t in df_tasks[df_tasks['event_date'] == d_str].iterrows():
                                    base_class = "task-item task-done" if t['status'] == '完了' else "task-item"
                                    if str(t['worker_id']) == '0': base_class += " task-general"
                                    cat_icon = "🛫" if t['category'] == "帰国手続き" else "🏢" if t[
                                                                                                 'category'] == "入管手続き" else "☑" if \
                                    t['status'] == '完了' else "▢"
                                    tasks_html += f"<div class='{base_class}'>{cat_icon} {str(t['name_en'])[:4]}: {t['task_name']}</div>"

                        if cal_filter in ["すべて表示", "走行距離のみ表示"]:
                            if not df_mileage.empty and 'record_date' in df_mileage.columns:
                                for _, m_row in df_mileage[df_mileage['record_date'] == d_str].iterrows():
                                    tasks_html += f"<div class='task-item task-mileage'>🚗 {m_row.get('driven_km', 0)}km ({str(m_row.get('driver_name', '')).replace('青山（', '').replace('）', '')})</div>"

                        st.markdown(f'<div class="cal-cell" style="{bg_style}">{html}{tasks_html}</div>',
                                    unsafe_allow_html=True)
                    else:
                        st.markdown('<div class="cal-cell" style="background-color:#1e1e1e; border:none;"></div>',
                                    unsafe_allow_html=True)

    with col_panel:
        st.markdown("### 🛠️ 日別操作パネル")
        target_date_obj = st.date_input("操作する日付", t_date, key="panel_target_date")
        target_str = target_date_obj.strftime("%Y-%m-%d")
        st.divider()
        st.markdown(f"**【{target_str} の予定】**")

        has_plan = False
        if not df_tasks.empty:
            for _, t in df_tasks[df_tasks['event_date'] == target_str].iterrows():
                has_plan = True
                is_done = t['status'] == '完了'
                cat_badge = f"【{t['category']}】" if t['category'] != "一般業務" else ""
                st.markdown(f"**{'☑' if is_done else '▢'} {str(t['name_en'])[:4]}**: {cat_badge}{t['task_name']}")
                c1, c2 = st.columns(2)
                if c1.button("完了/取消", key=f"tg_{t['id']}", use_container_width=True):
                    db.collection('events_logs').document(str(t['id'])).update({"status": "未完了" if is_done else "完了"})
                    clear_caches();
                    st.rerun()
                if c2.button("🗑️ 削除", key=f"del_{t['id']}", use_container_width=True):
                    db.collection('events_logs').document(str(t['id'])).delete()
                    clear_caches();
                    st.rerun()
                st.write("---")

        if not df_mileage.empty and 'record_date' in df_mileage.columns:
            for _, m_row in df_mileage[df_mileage['record_date'] == target_str].iterrows():
                has_plan = True
                st.markdown(
                    f"**🚗 走行**: {m_row.get('driven_km', 0)}km ({str(m_row.get('driver_name', '')).replace('青山（', '').replace('）', '')})")
                if st.button("🗑️ 削除", key=f"del_m_{m_row['id']}", use_container_width=True):
                    db.collection('mileage_logs').document(str(m_row['id'])).delete()
                    clear_caches();
                    st.rerun()
                st.write("---")

        if not has_plan: st.caption("予定はありません")
        st.divider()

        st.markdown("**➕ 新規追加**")
        with st.expander("👤 外国人材タスクを追加"):
            df_w = fetch_all_cached("foreign_workers")
            if not df_w.empty and not df_comp_all.empty:
                df_w = df_w[df_w['company_id'].isin(valid_company_ids)]
                df_w = pd.merge(df_w, df_comp_all[['id', 'company_name']], left_on='company_id', right_on='id',
                                how='left')
                if not df_w.empty:
                    s_c = st.selectbox("会社", sorted(df_w['company_name'].dropna().unique()), key="add_w_c")
                    df_sub = df_w[df_w['company_name'] == s_c]
                    s_w = st.selectbox("対象者", df_sub['id_x'].tolist(),
                                       format_func=lambda x: df_sub[df_sub['id_x'] == x]['name_en'].values[0],
                                       key="add_w_w")

                    mode = st.radio("追加方法", ["単発", "テンプレート"], horizontal=True, key="add_w_m")
                    if mode == "単発":
                        task_cat = st.selectbox("タスクカテゴリ", ["一般業務", "帰国手続き", "入管手続き"], key="add_w_cat")
                        tn = st.text_input("タスク名", key="add_w_t")
                        if st.button("追加", key="btn_add_w"):
                            db.collection('events_logs').add({
                                "worker_id": str(s_w), "task_name": str(tn), "category": str(task_cat),
                                "event_date": target_str, "status": "未完了", "created_at": firestore.SERVER_TIMESTAMP
                            })
                            db.collection('worker_logs').add({
                                "worker_id": str(s_w), "log_date": target_str,
                                "log_content": f"【タスク登録/{task_cat}】{str(tn)}",
                                "created_at": firestore.SERVER_TIMESTAMP
                            })
                            clear_caches();
                            st.rerun()
                    else:
                        t_df = fetch_all_cached("task_templates")
                        if not t_df.empty:
                            tid = st.selectbox("テンプレート", t_df['id'].tolist(),
                                               format_func=lambda x: t_df[t_df['id'] == x]['template_name'].values[0],
                                               key="add_w_tpl")
                            if st.button("一括追加", key="btn_add_w_tpl"):
                                d_df = fetch_where("template_details", "template_id", "==", tid)
                                for _, d in d_df.iterrows():
                                    evd = (target_date_obj + timedelta(days=int(d['offset_days']))).strftime("%Y-%m-%d")
                                    db.collection('events_logs').add({
                                        "worker_id": str(s_w), "task_name": str(d['task_name']), "category": "一般業務",
                                        "event_date": evd, "status": "未完了", "created_at": firestore.SERVER_TIMESTAMP
                                    })
                                    db.collection('worker_logs').add({
                                        "worker_id": str(s_w), "log_date": evd,
                                        "log_content": f"【タスク登録】{str(d['task_name'])}",
                                        "created_at": firestore.SERVER_TIMESTAMP
                                    })
                                clear_caches();
                                st.rerun()

        with st.expander("🏢 一般・会社タスクを追加"):
            if not df_comp_all.empty:
                df_c_sub = df_comp_all[df_comp_all['id'].isin(valid_company_ids)]
                c_opts = ['0'] + df_c_sub['id'].tolist()
                c_names = ["指定なし（一般業務）"] + df_c_sub['company_name'].tolist()
                s_c_gen = st.selectbox("対象の会社", c_opts, format_func=lambda x: c_names[c_opts.index(x)], key="add_g_c")
                tn_gen = st.text_input("タスク名", key="add_g_t")
                if st.button("追加", key="btn_add_g"):
                    t_name = f"[{c_names[c_opts.index(s_c_gen)]}] {str(tn_gen)}" if s_c_gen != '0' else str(tn_gen)
                    db.collection('events_logs').add({
                        "worker_id": "0", "company_id": None if s_c_gen == '0' else str(s_c_gen), "task_name": t_name,
                        "category": "一般業務", "event_date": target_str, "status": "未完了",
                        "created_at": firestore.SERVER_TIMESTAMP
                    })
                    if s_c_gen != '0':
                        db.collection('company_logs').add(
                            {"company_id": str(s_c_gen), "log_date": target_str, "log_category": "一般",
                             "log_content": f"【タスク登録】{str(tn_gen)}", "created_at": firestore.SERVER_TIMESTAMP})
                    clear_caches();
                    st.rerun()

        with st.expander("🚗 走行距離を記録"):
            dr_direct = st.selectbox("運転者", ["青山（妻）", "青山（夫）", "スタッフ"], key="add_m_dr")
            dist = st.number_input("距離 (km)", value=0, min_value=0, step=1, key="add_m_d")
            if st.button("記録する", key="btn_add_m"):
                if dist > 0:
                    last_end_km = 0
                    if not df_mileage.empty and 'end_km' in df_mileage.columns:
                        try:
                            last_end_km = int(
                                df_mileage.sort_values(by="record_date", ascending=False).iloc[0].get('end_km', 0))
                        except:
                            pass
                    db.collection('mileage_logs').add(
                        {"record_date": target_str, "driver_name": str(dr_direct), "start_km": int(last_end_km),
                         "end_km": int(last_end_km + dist), "driven_km": int(dist)})
                    clear_caches();
                    st.rerun()
                else:
                    st.warning("距離を入力してください")


# ==========================================
# 👥 画面：人材名簿
# ==========================================
def show_worker_list():
    st.title("👥 人材名簿")
    df_w = fetch_all_cached("foreign_workers")
    df_all_logs = fetch_all_cached("worker_logs")

    if df_w.empty or df_comp_all.empty: st.info("データがありません"); return

    df_w = df_w[df_w['company_id'].isin(valid_company_ids)]
    df = pd.merge(df_w, df_comp_all[['id', 'company_name', 'address']], left_on='company_id', right_on='id',
                  how='left').rename(columns={'address': 'comp_address', 'id_x': 'id'})
    df['visa_order'] = df['visa_status'].map(
        {'技能実習1号': 1, '技能実習2号': 2, '技能実習3号': 3, '特定活動': 4, '特定技能1号': 5, '特定技能2号': 6}).fillna(7)

    if 'enrollment_status' not in df.columns:
        df['enrollment_status'] = '在籍中'
    else:
        df['enrollment_status'] = df['enrollment_status'].fillna('在籍中')

    df = df.sort_values(by=['company_name', 'visa_order', 'entry_date'], ascending=[True, True, True])

    st.markdown("### 🔍 対象者の絞り込み・検索")
    enroll_filter = st.radio("表示する在籍状況", ["在籍中", "非在籍中", "すべて表示"], horizontal=True)
    if enroll_filter != "すべて表示":
        df = df[df['enrollment_status'] == enroll_filter]

    c1, c2 = st.columns(2)
    comp_search = c1.text_input("🏢 会社名で検索（部分一致）")
    name_search = c2.text_input("👤 名前で検索（部分一致）")

    if comp_search: df = df[df['company_name'].str.contains(comp_search, case=False, na=False)]
    if name_search: df = df[df['name_en'].str.contains(name_search, case=False, na=False)]
    if df.empty: st.warning("該当者なし"); return

    st.divider()
    worker_options = df.apply(
        lambda r: f"[{r['company_name']}] {r['name_en']} ({r['visa_status']} / 入国日：{format_date(r.get('entry_date'))})",
        axis=1).tolist()
    selected_label = st.selectbox("👇 リストから対象者を選択してください", worker_options)

    selected_id = str(df['id'].tolist()[worker_options.index(selected_label)])
    w = df[df['id'] == selected_id].iloc[0]

    st.markdown(f"## 👤 {w['name_en']} さんの詳細データ")

    tab_info, tab_log, tab_files, tab_edit = st.tabs(["📋 基本情報", "📝 ログ・履歴", "📁 書類管理", "✏️ 登録情報の編集"])

    with tab_info:
        col_img, col_p, col_v, col_c = st.columns([1.5, 3, 3, 3])
        with col_img:
            img_val = str(w.get('photo_path', ''))
            if img_val.startswith('http'):
                st.image(img_val, use_container_width=True)
            else:
                st.info("📷 未登録")

            if w.get('enrollment_status') == '非在籍中':
                st.error("非在籍（退職等）")
            else:
                st.success("在籍中")

        col_p.markdown(
            f"##### 👤 本人情報\n<div style='line-height:1.6; font-size:14px;'><b>氏名カナ</b><br>{format_date(w.get('name_kana'))}<br><br><b>ニックネーム</b><br>{format_date(w.get('nickname'))}<br><br><b>生年月日</b><br>{format_date(w.get('birthdate'))}<br><br><b>性別</b><br>{format_date(w.get('gender'))}<br><br><b>国籍</b><br>{format_date(w.get('nationality'))}<br><br><b>出身地</b><br>{format_date(w.get('birthplace'))}<br><br><b>本国居住地</b><br>{format_date(w.get('home_address'))}</div>",
            unsafe_allow_html=True)
        # 🌟 修正ポイント：「在留カード期限」に変更
        col_v.markdown(
            f"##### ✈️ 在留・資格情報\n<div style='line-height:1.6; font-size:14px;'><b>在留資格</b><br>{format_date(w.get('visa_status'))}<br><br><b>在留カード期限</b><br>{format_date(w.get('visa_expiry'))}<br><br><b>在留カード番号</b><br>{format_date(w.get('residence_card_number'))}<br><br><b>在留カード期間(月)</b><br>{format_date(w.get('residence_card_duration_months'))}<br><br><b>特定1号期間</b><br>{format_date(w.get('ssw1_start_date'))} 〜 {format_date(w.get('ssw1_end_date'))}<br><br><b>特定2号開始日</b><br>{format_date(w.get('ssw2_start_date'))}</div>",
            unsafe_allow_html=True)
        col_c.markdown(
            f"##### 🏢 所属・給与等\n<div style='line-height:1.6; font-size:14px;'><b>入国日</b><br>{format_date(w.get('entry_date'))}<br><br><b>パスポート番号</b><br>{format_date(w.get('passport_number'))}<br><br><b>パスポート期限</b><br>{format_date(w.get('passport_expiration_date'))}<br><br><b>時給 / 日給 / 月給</b><br>{format_date(w.get('hourly_wage'))} / {format_date(w.get('daily_wage'))} / {format_date(w.get('monthly_wage'))}<br><br><b>居住費</b><br>{format_date(w.get('housing_cost'))}<br><br><b>宿舎・寮住所</b><br>{format_date(w.get('residence_address'))}<br><br><b>斡旋機関</b><br>{format_date(w.get('dispatch_agency'))}<br><br><b>パスポート・在留カード保管先</b><br>{format_date(w.get('document_status'))}<br><br><b>備考</b><br>{format_date(w.get('remarks'))}</div>",
            unsafe_allow_html=True)

    with tab_log:
        log_df = df_all_logs[df_all_logs['worker_id'] == selected_id].sort_values(by="log_date",
                                                                                  ascending=False) if not df_all_logs.empty else pd.DataFrame()
        with st.form(f"log_form_{selected_id}"):
            c_d, c_t = st.columns([1, 3])
            l_date = c_d.date_input("日付", datetime.now())
            l_text = c_t.text_input("ログ内容")
            if st.form_submit_button("＋ 追加"):
                db.collection('worker_logs').add(
                    {"worker_id": selected_id, "log_date": l_date.strftime("%Y-%m-%d"), "log_content": str(l_text),
                     "created_at": firestore.SERVER_TIMESTAMP})
                clear_caches();
                st.rerun()

        for _, l in log_df.iterrows():
            with st.expander(f"📅 {l['log_date']} ： {l.get('log_content', '')}"):
                with st.form(f"edit_w_log_{l['id']}"):
                    edit_txt = st.text_input("内容の編集", value=l.get('log_content', ''))
                    ec1, ec2 = st.columns(2)
                    if ec1.form_submit_button("💾 変更を保存", use_container_width=True):
                        db.collection('worker_logs').document(l['id']).update({"log_content": str(edit_txt)})
                        clear_caches();
                        st.success("保存しました！");
                        st.rerun()
                    if ec2.form_submit_button("🗑️ ログを削除", use_container_width=True):
                        db.collection('worker_logs').document(l['id']).delete()
                        clear_caches();
                        st.warning("削除しました");
                        st.rerun()

    with tab_files:
        manage_files_ui(f"workers/{selected_id}/files", label=f"{w['name_en']} さんの書類")

    with tab_edit:
        st.subheader(f"👤 {w['name_en']} さんの文字情報・写真修正")
        col_edit_img, col_edit_form = st.columns([1, 3])
        with col_edit_img:
            st.write("📷 **新しい写真の登録**")
            if "uploader_key" not in st.session_state: st.session_state.uploader_key = str(time.time())
            new_photo = st.file_uploader("写真を選択", type=["jpg", "png", "jpeg"], key=st.session_state.uploader_key)
            if new_photo and st.button("🚀 写真を保存", type="primary", key=f"btn_p_save_{selected_id}"):
                import io
                img = Image.open(new_photo);
                img = ImageOps.exif_transpose(img)
                img_cropped = ImageOps.fit(img, (600, 800), method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))
                if img_cropped.mode in ("RGBA", "P"): img_cropped = img_cropped.convert("RGB")
                img_byte_arr = io.BytesIO();
                img_cropped.save(img_byte_arr, format='JPEG', quality=85);
                img_byte_arr.seek(0)

                class DummyFile:
                    def __init__(self, f): self.f = f; self.type = "image/jpeg"

                    def read(self, *args): return self.f.read(*args)

                    def tell(self): return self.f.tell()

                    def seek(self, *args): return self.f.seek(*args)

                with st.spinner('送信中...'):
                    url = upload_image_to_storage(DummyFile(img_byte_arr), selected_id)
                    if url:
                        db.collection('foreign_workers').document(selected_id).update({"photo_path": url})
                        clear_caches();
                        st.success("写真を更新しました！");
                        time.sleep(1);
                        st.session_state.uploader_key = str(time.time());
                        st.rerun()

            current_photo = str(w.get('photo_path', ''))
            if current_photo.startswith('http'):
                st.markdown("---")
                st.write("🗑️ **現在の写真を削除**")
                if st.button("写真を削除する", type="secondary", key=f"btn_p_del_{selected_id}"):
                    db.collection('foreign_workers').document(selected_id).update({"photo_path": ""})
                    clear_caches();
                    st.success("写真を削除しました！");
                    time.sleep(1);
                    st.rerun()

        with col_edit_form:
            with st.form(f"edit_worker_info_form_{selected_id}"):
                n_enroll = st.selectbox("在籍状況", ["在籍中", "非在籍中"],
                                        index=0 if w.get('enrollment_status', '在籍中') == '在籍中' else 1)
                nc = st.selectbox("所属会社（移籍）", df_comp_all['company_name'].tolist(),
                                  index=df_comp_all['company_name'].tolist().index(w['company_name']))
                ncid = str(df_comp_all[df_comp_all['company_name'] == nc]['id'].values[0])

                st.markdown("---")
                e1, e2 = st.columns(2)
                with e1:
                    nkana = st.text_input("氏名カナ", value=format_date(w.get('name_kana', '')))
                    nbirth = st.text_input("生年月日", value=format_date(w.get('birthdate', '')))
                    nnat = st.text_input("国籍", value=format_date(w.get('nationality', '')))
                with e2:
                    nnick = st.text_input("ニックネーム", value=format_date(w.get('nickname', '')))
                    ngender = st.text_input("性別", value=format_date(w.get('gender', '')))
                    nentry = st.text_input("入国日", value=format_date(w.get('entry_date', '')))

                st.markdown("---")
                e3, e4 = st.columns(2)
                with e3:
                    nvisa = st.selectbox("在留資格",
                                         ["技能実習1号", "技能実習2号", "技能実習3号", "特定技能1号", "特定技能2号", "特定活動", "その他"],
                                         index=["技能実習1号", "技能実習2号", "技能実習3号", "特定技能1号", "特定技能2号", "特定活動",
                                                "その他"].index(w.get('visa_status', '技能実習1号')) if w.get('visa_status',
                                                                                                      '技能実習1号') in [
                                                                                                          "技能実習1号",
                                                                                                          "技能実習2号",
                                                                                                          "技能実習3号",
                                                                                                          "特定技能1号",
                                                                                                          "特定技能2号",
                                                                                                          "特定活動",
                                                                                                          "その他"] else 0)
                    nrc_n = st.text_input("在留カード番号", value=format_date(w.get('residence_card_number', '')))
                    npass_n = st.text_input("パスポート番号", value=format_date(w.get('passport_number', '')))
                with e4:
                    def safe_date_parse(date_str):
                        if pd.isna(date_str) or str(date_str).strip() in ["", "nan", "None",
                                                                          "ー"]: return datetime.now().date()
                        try:
                            return datetime.strptime(str(date_str).strip()[:10], '%Y-%m-%d').date()
                        except:
                            try:
                                return datetime.strptime(str(date_str).strip()[:10], '%Y/%m/%d').date()
                            except:
                                return datetime.now().date()

                    # 🌟 修正ポイント：「在留カード期限」に変更
                    nv = st.date_input("在留カード期限", safe_date_parse(w.get('visa_expiry', '')))
                    # 🌟 修正ポイント：「在留カード期間」に変更
                    nrc_dur = st.text_input("在留カード期間（月単位、例:18ヶ月）",
                                            value=format_date(w.get('residence_card_duration_months', '')))
                    np_exp = st.date_input("パスポート期限", safe_date_parse(w.get('passport_expiration_date', '')))

                st.markdown("---")
                e5, e6 = st.columns(2)
                with e5:
                    nssw1_s = st.text_input("特定技能1号開始日 (手入力 例:2024/01/01)",
                                            value=format_date(w.get('ssw1_start_date', '')))
                    nssw2_s = st.text_input("特定技能2号開始日 (手入力 例:2025/01/01)",
                                            value=format_date(w.get('ssw2_start_date', '')))
                with e6:
                    nssw1_e = st.text_input("特定技能1号終了日 (手入力 例:2024/12/31)",
                                            value=format_date(w.get('ssw1_end_date', '')))

                st.markdown("---")
                e7, e8 = st.columns(2)
                with e7:
                    nwage_h = st.text_input("時給 (円)", value=format_date(w.get('hourly_wage', '')))
                    # 🌟 追加：月給入力欄を追加
                    nwage_m = st.text_input("月給 (円)", value=format_date(w.get('monthly_wage', '')))
                    nr = st.text_input("宿舎・寮住所", value=format_date(w.get('residence_address', '')))
                    nrem = st.text_input("備考", value=format_date(w.get('remarks', '')))
                with e8:
                    nwage_d = st.text_input("日給 (円)", value=format_date(w.get('daily_wage', '')))
                    nhousing = st.text_input("居住費", value=format_date(w.get('housing_cost', '')))
                    nagency = st.text_input("斡旋機関", value=format_date(w.get('dispatch_agency', '')))

                st.markdown("---")
                confirm_save = st.checkbox("上記の内容で保存（上書き）することを確認しました", key=f"chk_save_{selected_id}")

                if st.form_submit_button("💾 変更をすべて保存する"):
                    if confirm_save:
                        db.collection('foreign_workers').document(selected_id).update({
                            "enrollment_status": str(n_enroll),
                            "company_id": ncid,
                            "name_kana": str(nkana),
                            "nickname": str(nnick),
                            "birthdate": str(nbirth),
                            "gender": str(ngender),
                            "nationality": str(nnat),
                            "visa_status": str(nvisa),
                            "visa_expiry": nv.strftime('%Y-%m-%d'),
                            "residence_card_number": str(nrc_n),
                            "residence_card_duration_months": str(nrc_dur),
                            "passport_number": str(npass_n),
                            "passport_expiration_date": np_exp.strftime('%Y-%m-%d'),
                            "ssw1_start_date": str(nssw1_s),
                            "ssw1_end_date": str(nssw1_e),
                            "ssw2_start_date": str(nssw2_s),
                            "entry_date": str(nentry),
                            "hourly_wage": str(nwage_h),
                            "daily_wage": str(nwage_d),
                            # 🌟 追加：月給の保存
                            "monthly_wage": str(nwage_m),
                            "housing_cost": str(nhousing),
                            "residence_address": str(nr),
                            "dispatch_agency": str(nagency),
                            "remarks": str(nrem)
                        })
                        clear_caches();
                        st.success("名簿情報を更新しました！");
                        st.rerun()
                    else:
                        st.error("※ 保存する場合は、「確認しました」のチェックを入れてからボタンを押してください。")

        st.markdown("---")
        st.markdown("##### 🗑️ 人材データの削除")
        with st.form(f"del_worker_form_{selected_id}"):
            st.warning("この操作は取り消せません。削除する場合はチェックを入れてボタンを押してください。")
            confirm_del = st.checkbox("本当にこの人材のデータをすべて削除することを確認しました", key=f"chk_del_{selected_id}")
            if st.form_submit_button("🗑️ この人材を削除する"):
                if confirm_del:
                    db.collection('foreign_workers').document(selected_id).delete()
                    clear_caches()
                    st.success("人材データを削除しました。")
                    time.sleep(1.5)
                    st.rerun()
                else:
                    st.error("※ 削除する場合は、確認のチェックを入れてください。")


# ==========================================
# 🏢 画面：会社情報
# ==========================================
def show_company_details():
    st.title("🏢 会社情報")
    if df_comp_all.empty: st.warning("会社が登録されていません。"); return

    df_c = df_comp_all[df_comp_all['id'].isin(valid_company_ids)]
    comp_search = st.text_input("🔍 会社名で検索（部分一致）", placeholder="例：青山", key="comp_details_page_search")
    if comp_search:
        df_c = df_c[df_c['company_name'].str.contains(comp_search, case=False, na=False)]

    if df_c.empty:
        st.warning("該当する会社がありません。検索条件を変えてみてください。")
        return

    c_name = st.selectbox("対象の会社を選択してください", df_c['company_name'].tolist())

    c_data = df_c[df_c['company_name'] == c_name].iloc[0]
    c_id = str(c_data['id'])

    tab_info, tab_log, tab_file = st.tabs(["📋 基本情報・設定", "📝 カテゴリ別ログ", "📁 共有フォルダ"])

    with tab_info:
        with st.form("comp_edit_form"):
            st.markdown("##### ⚙️ 会社基本情報・各種設定")

            c1, c2 = st.columns(2)
            with c1:
                rep_name = st.text_input("代表者氏名", value=format_date(c_data.get('representative_name', '')))
            with c2:
                rep_kana = st.text_input("代表者氏名（カナ）",
                                         value=format_date(c_data.get('representative_name_kana', '')))

            c_address = st.text_input("🏢 会社住所", value=format_date(c_data.get('address', '')))
            industry = st.text_input("特定産業分野", value=format_date(c_data.get('specific_industry_field', '')))

            st.markdown("---")
            c3, c4 = st.columns(2)

            def safe_date_parse_comp(date_str):
                if pd.isna(date_str) or str(date_str).strip() in ["", "nan", "None",
                                                                  "ー"]: return datetime.now().date()
                try:
                    return datetime.strptime(str(date_str).strip()[:10], '%Y-%m-%d').date()
                except:
                    try:
                        return datetime.strptime(str(date_str).strip()[:10], '%Y/%m/%d').date()
                    except:
                        return datetime.now().date()

            with c3:
                work_addr = st.text_input("実習場所住所", value=format_date(c_data.get('workplace_address', '')))
                a36_start = st.date_input("36協定 起算日（ここから1年経過でアラート）",
                                          safe_date_parse_comp(c_data.get('agreement_36_start_date')))
                sup_tr = st.date_input("技能実習責任者講習日（ここから2.5年経過でアラート）",
                                       safe_date_parse_comp(c_data.get('supervisor_training_date')))

            with c4:
                work_tel = st.text_input("実習場所TEL", value=format_date(c_data.get('workplace_tel', '')))
                wp_opts = ["未確認", "◯", "✖"]
                wp_val = str(c_data.get('workplace_confirmed', '未確認'))
                wp = st.selectbox("実習場所確認", wp_opts, index=wp_opts.index(wp_val) if wp_val in wp_opts else 0)

            st.markdown("---")
            c5, c6 = st.columns(2)
            with c5:
                inst_mgr = st.text_input("指導責任者", value=format_date(c_data.get('instructor_manager', '')))
            with c6:
                v_hours = st.text_area("変形労働 備考",
                                       value=format_date(c_data.get('variable_working_hours_remarks', '')))

            if st.form_submit_button("💾 会社情報を保存"):
                db.collection('companies').document(c_id).update({
                    "representative_name": str(rep_name),
                    "representative_name_kana": str(rep_kana),
                    "address": str(c_address),
                    "specific_industry_field": str(industry),
                    "workplace_address": str(work_addr),
                    "workplace_tel": str(work_tel),
                    "agreement_36_start_date": a36_start.strftime('%Y-%m-%d'),
                    "supervisor_training_date": sup_tr.strftime('%Y-%m-%d'),
                    "workplace_confirmed": wp,
                    "instructor_manager": str(inst_mgr),
                    "variable_working_hours_remarks": str(v_hours)
                })
                clear_caches();
                st.success("保存しました！");
                st.rerun()

    with tab_log:
        st.markdown("##### 📝 業務ログ（指導員・検診・有給など）")
        log_cats = ["一般", "有給消化", "指導員", "特別教育", "健康診断", "その他軽微変更", "年末調整", "最賃確認", "キャリアアップ"]

        with st.form("c_log_add"):
            lc1, lc2, lc3 = st.columns([2, 2, 5])
            l_date = lc1.date_input("日付", datetime.now())
            l_cat = lc2.selectbox("カテゴリ", log_cats)
            l_text = lc3.text_input("記録内容")
            if st.form_submit_button("＋ ログ追加"):
                db.collection('company_logs').add({
                    "company_id": c_id, "log_date": l_date.strftime('%Y-%m-%d'),
                    "log_category": str(l_cat), "log_content": str(l_text), "created_at": firestore.SERVER_TIMESTAMP
                })
                clear_caches();
                st.success("追加しました！");
                st.rerun()

        c_logs = fetch_where("company_logs", "company_id", "==", c_id)
        if not c_logs.empty:
            if 'log_category' not in c_logs.columns:
                c_logs['log_category'] = '一般'
            else:
                c_logs['log_category'] = c_logs['log_category'].fillna('一般')

            filter_cat = st.radio("表示フィルター", ["すべて"] + log_cats, horizontal=True)
            if filter_cat != "すべて": c_logs = c_logs[c_logs['log_category'] == filter_cat]

            for _, l in c_logs.sort_values(by="log_date", ascending=False).iterrows():
                with st.expander(f"📅 {l['log_date']} 【{l['log_category']}】 ： {l.get('log_content', '')}"):
                    with st.form(f"edit_c_log_form_{l['id']}"):
                        e_txt = st.text_input("ログ内容変更", value=l.get('log_content', ''))
                        e_cat = st.selectbox("カテゴリ変更", log_cats, index=log_cats.index(l['log_category']))
                        eb1, eb2 = st.columns(2)
                        if eb1.form_submit_button("💾 修正内容を保存", use_container_width=True):
                            db.collection('company_logs').document(l['id']).update(
                                {"log_content": str(e_txt), "log_category": str(e_cat)})
                            clear_caches();
                            st.success("保存完了");
                            st.rerun()
                        if eb2.form_submit_button("🗑️ 削除する", use_container_width=True):
                            db.collection('company_logs').document(l['id']).delete()
                            clear_caches();
                            st.warning("削除完了");
                            st.rerun()

    with tab_file:
        manage_files_ui(f"companies/{c_id}/shared", label=f"{c_name} 共有")


# ==========================================
# 📝 画面：ログ一覧
# ==========================================
def show_logs_manager():
    st.title("📝 ログ一覧")

    t1, t2 = st.tabs(["🏢 会社関連のログ", "👤 人材（個人）のログ"])
    log_cats = ["一般", "有給消化", "指導員", "特別教育", "健康診断", "その他軽微変更", "年末調整", "最賃確認", "キャリアアップ"]

    with t1:
        if not df_comp_all.empty:
            df_c = df_comp_all[df_comp_all['id'].isin(valid_company_ids)]

            comp_search = st.text_input("🏢 会社名で検索（部分一致）", placeholder="例：青山", key="log_comp_search")
            if comp_search:
                df_c = df_c[df_c['company_name'].str.contains(comp_search, case=False, na=False)]

            if df_c.empty:
                st.warning("該当する会社がありません。検索条件を変えてみてください。")
            else:
                s_c = st.selectbox("会社を選択", df_c['id'].tolist(),
                                   format_func=lambda x: df_c[df_c['id'] == x]['company_name'].values[0],
                                   key="log_mgr_c_select")
                c_logs = fetch_where("company_logs", "company_id", "==", str(s_c))

                if not c_logs.empty:
                    for _, l in c_logs.sort_values(by="log_date", ascending=False).iterrows():
                        with st.expander(
                                f"📅 {l['log_date']} 【{l.get('log_category', '一般')}】 : {l.get('log_content', '')}"):
                            with st.form(f"mgr_edit_c_log_{l['id']}"):
                                t_input = st.text_input("ログ内容変更", value=l.get('log_content', ''))
                                cat_input = st.selectbox("カテゴリ変更", log_cats,
                                                         index=log_cats.index(l.get('log_category', '一般')) if l.get(
                                                             'log_category', '一般') in log_cats else 0)
                                b1, b2 = st.columns(2)
                                if b1.form_submit_button("💾 保存", use_container_width=True):
                                    db.collection('company_logs').document(l['id']).update(
                                        {"log_content": str(t_input), "log_category": str(cat_input)})
                                    clear_caches();
                                    st.rerun()
                                if b2.form_submit_button("🗑️ 削除", use_container_width=True):
                                    db.collection('company_logs').document(l['id']).delete()
                                    clear_caches();
                                    st.rerun()
                else:
                    st.write("該当するログはありません。")
        else:
            st.write("登録されている会社がありません。")

    with t2:
        df_w = fetch_all_cached("foreign_workers")
        if not df_w.empty and not df_comp_all.empty:
            df_w = df_w[df_w['company_id'].isin(valid_company_ids)]
            df_w = pd.merge(df_w, df_comp_all[['id', 'company_name']], left_on='company_id', right_on='id', how='left')

            lc1, lc2 = st.columns(2)
            with lc1:
                w_comp_search = st.text_input("🏢 会社名で検索（部分一致）", placeholder="例：青山", key="log_w_comp_search")
            with lc2:
                w_name_search = st.text_input("👤 名前で検索（部分一致）", placeholder="例：John", key="log_w_name_search")

            if w_comp_search:
                df_w = df_w[df_w['company_name'].str.contains(w_comp_search, case=False, na=False)]
            if w_name_search:
                df_w = df_w[df_w['name_en'].str.contains(w_name_search, case=False, na=False)]

            if df_w.empty:
                st.warning("該当する対象者がいません。検索条件を変えてみてください。")
            else:
                s_w = st.selectbox("対象者を選択", df_w['id_x'].tolist(), format_func=lambda
                    x: f"[{df_w[df_w['id_x'] == x]['company_name'].values[0]}] {df_w[df_w['id_x'] == x]['name_en'].values[0]}")
                w_logs = fetch_where("worker_logs", "worker_id", "==", str(s_w))

                if not w_logs.empty:
                    for _, l in w_logs.sort_values(by="log_date", ascending=False).iterrows():
                        with st.expander(f"📅 {l['log_date']} : {l.get('log_content', '')}"):
                            with st.form(f"mgr_edit_w_log_{l['id']}"):
                                t_w_input = st.text_input("ログ内容変更", value=l.get('log_content', ''))
                                wb1, wb2 = st.columns(2)
                                if wb1.form_submit_button("💾 保存", use_container_width=True):
                                    db.collection('worker_logs').document(l['id']).update(
                                        {"log_content": str(t_w_input)})
                                    clear_caches();
                                    st.rerun()
                                if wb2.form_submit_button("🗑️ 削除", use_container_width=True):
                                    db.collection('worker_logs').document(l['id']).delete()
                                    clear_caches();
                                    st.rerun()
                else:
                    st.write("該当するログはありません。")
        else:
            st.write("登録されている人材データがありません。")


# ==========================================
# ➕ 画面：新規登録
# ==========================================
def show_add_new():
    st.title("➕ 新規登録")
    t1, t2 = st.tabs(["🏢 会社の新規登録", "👤 外国人材の新規登録"])
    with t1:
        with st.form("c"):
            cn = st.text_input("会社名")
            ca = st.selectbox("地域", ["近畿", "関東", "東海", "静岡", "九州", "中四国", "北信越", "北海道・東北"])
            c_addr_new = st.text_input("🏢 会社住所", placeholder="例：大阪府大阪市...")

            confirm_new_c = st.checkbox("二重登録ではないことを確認しました", key="chk_new_c")
            if st.form_submit_button("登録"):
                if cn and confirm_new_c:
                    db.collection('companies').add({
                        "company_name": str(cn),
                        "area": str(ca),
                        "address": str(c_addr_new),
                        "created_at": firestore.SERVER_TIMESTAMP
                    })
                    clear_caches();
                    st.success("登録完了");
                    st.rerun()
                elif not confirm_new_c:
                    st.error("※ 登録する場合は、「確認しました」のチェックを入れてください。")
                else:
                    st.error("会社名を入力してください。")

    with t2:
        if not df_comp_all.empty:
            df_c = df_comp_all[df_comp_all['id'].isin(valid_company_ids)]
            with st.form("w"):
                comp = str(st.selectbox("所属", df_c['id'].tolist(),
                                        format_func=lambda x: df_c[df_c['id'] == x]['company_name'].values[0]))
                name = st.text_input("氏名")
                visa = st.selectbox("資格", ["技能実習1号", "技能実習2号", "技能実習3号", "特定技能1号", "特定技能2号", "特定活動", "その他"])

                confirm_new_w = st.checkbox("二重登録ではないことを確認しました", key="chk_new_w")
                if st.form_submit_button("登録"):
                    if name and confirm_new_w:
                        db.collection('foreign_workers').add(
                            {"company_id": comp, "name_en": str(name), "visa_status": str(visa), "is_away": 0,
                             "document_status": "本人所持", "enrollment_status": "在籍中",
                             "created_at": firestore.SERVER_TIMESTAMP})
                        clear_caches();
                        st.success("登録完了");
                        st.rerun()
                    elif not confirm_new_w:
                        st.error("※ 登録する場合は、「確認しました」のチェックを入れてください。")
                    else:
                        st.error("氏名を入力してください。")


# ==========================================
# ⚙️ 画面：テンプレート設定
# ==========================================
def show_tpl_set():
    st.title("⚙️ テンプレート設定")
    with st.form("t"):
        tn = st.text_input("新規テンプレート名")
        if st.form_submit_button("作成"):
            db.collection('task_templates').add({"template_name": str(tn), "created_at": firestore.SERVER_TIMESTAMP})
            clear_caches();
            st.rerun()

    df_t = fetch_all_cached("task_templates")
    if not df_t.empty:
        stn = st.selectbox("編集するテンプレート", df_t['id'].tolist(),
                           format_func=lambda x: df_t[df_t['id'] == x]['template_name'].values[0])
        if st.button("🗑️ テンプレートを削除"):
            db.collection('task_templates').document(stn).delete()
            for d_id in fetch_where("template_details", "template_id", "==", stn)['id']:
                db.collection('template_details').document(d_id).delete()
            clear_caches();
            st.rerun()
        st.divider()

        df_d = fetch_where("template_details", "template_id", "==", stn)
        if not df_d.empty:
            df_d['offset_days'] = pd.to_numeric(df_d['offset_days'])
            st.table(df_d.sort_values(by="offset_days")[['task_name', 'offset_days']])
            del_id = st.selectbox("削除する詳細", df_d['id'].tolist(),
                                  format_func=lambda x: df_d[df_d['id'] == x]['task_name'].values[0])
            if st.button("❌ 削除"):
                db.collection('template_details').document(del_id).delete()
                clear_caches();
                st.rerun()
        with st.form("ad"):
            dn = st.text_input("タスク内容")
            do = st.number_input("日数", value=0)
            if st.form_submit_button("追加"):
                db.collection('template_details').add(
                    {"template_id": stn, "task_name": str(dn), "offset_days": int(do)})
                clear_caches();
                st.rerun()


# ==========================================
# 🚗 画面：走行距離入力
# ==========================================
def show_mileage():
    st.title("🚗 走行距離入力")
    df_m = fetch_all_cached("mileage_logs")
    last_end_km = 0
    if not df_m.empty and 'end_km' in df_m.columns:
        try:
            last_end_km = int(df_m.sort_values(by="record_date", ascending=False).iloc[0].get('end_km', 0))
        except:
            pass

    if 'm_start' not in st.session_state: st.session_state.m_start = last_end_km
    if 'm_end' not in st.session_state: st.session_state.m_end = last_end_km

    t1, t2 = st.tabs(["🔢 メーター", "📏 距離直接"])
    with t1:
        with st.container():
            d_meter = st.date_input("日付", datetime.now(), key="date_meter")
            dr_meter = st.selectbox("運転者", ["青山（妻）", "青山（夫）", "スタッフ"], key="driver_meter")
            c1, c2 = st.columns(2)
            with c1:
                s_meter = st.number_input("出発(km)", value=int(st.session_state.m_start), step=1)
            with c2:
                e_meter = st.number_input("帰宅(km)", value=int(st.session_state.m_end), step=1)
            driven = e_meter - s_meter
            st.info(f"今回の走行距離: **{driven} km**")
            if st.button("💾 保存", type="primary"):
                if driven < 0:
                    st.error("エラー")
                else:
                    db.collection('mileage_logs').add(
                        {"record_date": d_meter.strftime("%Y-%m-%d"), "driver_name": str(dr_meter),
                         "start_km": int(s_meter), "end_km": int(e_meter), "driven_km": int(driven)})
                    st.session_state.m_start = e_meter;
                    st.session_state.m_end = e_meter
                    clear_caches();
                    st.success("保存！");
                    time.sleep(1);
                    st.rerun()
    with t2:
        with st.container():
            d_direct = st.date_input("日付", datetime.now(), key="date_direct")
            dr_direct = st.selectbox("運転者", ["青山（妻）", "青山（夫）", "スタッフ"], key="driver_direct")
            dist = st.number_input("距離 (km)", value=0, min_value=0, step=1)
            if st.button("💾 記録", type="primary"):
                if dist > 0:
                    new_end = last_end_km + dist
                    db.collection('mileage_logs').add(
                        {"record_date": d_direct.strftime("%Y-%m-%d"), "driver_name": str(dr_direct),
                         "start_km": int(last_end_km), "end_km": int(new_end), "driven_km": int(dist)})
                    st.session_state.m_start = new_end;
                    st.session_state.m_end = new_end
                    clear_caches();
                    st.success("保存！");
                    time.sleep(1);
                    st.rerun()


# ==========================================
# 🔄 画面ルーティング
# ==========================================
if page == "🏠 ダッシュボード":
    show_dashboard()
elif page == "🗓️ カレンダー":
    show_calendar()
elif page == "👥 人材名簿":
    show_worker_list()
elif page == "🏢 会社情報":
    show_company_details()
elif page == "📝 ログ一覧":
    show_logs_manager()
elif page == "➕ 新規登録":
    show_add_new()
elif page == "⚙️ テンプレート設定":
    show_tpl_set()
elif page == "🚗 走行距離入力":
    show_mileage()