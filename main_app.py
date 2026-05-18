import streamlit as st
import pandas as pd
import holidays
import os
import time
from datetime import datetime, timedelta
import calendar
from PIL import Image, ImageOps

# ==========================================
# 🔥 Firebase設定
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
                st.session_state["password_correct"] = True;
                st.rerun()
            else:
                st.error("❌ パスワードが間違っています。")
        st.stop()


check_password()


# ==========================================
# 🚀 爆速化・共通関数
# ==========================================
@st.cache_data(ttl=300)
def fetch_all_cached(collection_name):
    docs = db.collection(collection_name).stream()
    return pd.DataFrame([{"id": str(doc.id), **doc.to_dict()} for doc in docs])  # int64対策でIDを確実にstr化


def clear_caches(): st.cache_data.clear()


def fetch_where(collection_name, field, op, value):
    docs = db.collection(collection_name).where(field, op, value).stream()
    return pd.DataFrame([{"id": str(doc.id), **doc.to_dict()} for doc in docs])


def format_date(d): return "ー" if pd.isna(d) or str(d).strip() in ["None", "", "nan", "1900-01-01"] else str(d)


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
        st.error(f"エラー: {e}");
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
            st.success("アップロード完了！");
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
            if col_del.button("🗑️", key=f"del_{b.name}"): b.delete(); st.rerun()


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
    "🏠 ダッシュボード", "🗓️ カレンダー", "👥 外国人材名簿", "📝 名簿編集",
    "🏢 会社詳細・ファイル", "📝 ログ", "➕ 名簿へ新規追加", "⚙️ テンプレート設定", "🚗 走行距離入力"
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

    col1, col2 = st.columns([6, 4])
    with col1:
        st.subheader("📋 タスク一覧")
        df_tasks = fetch_all_cached("events_logs")
        df_workers = fetch_all_cached("foreign_workers")
        if not df_tasks.empty:
            if not df_workers.empty:
                df_tasks = pd.merge(df_tasks, df_workers[['id', 'name_en', 'company_id']], left_on='worker_id',
                                    right_on='id', how='left', suffixes=('', '_w'))
            else:
                df_tasks['name_en'] = '一般'; df_tasks['company_id'] = None
            if not df_comp_all.empty:
                df_tasks = pd.merge(df_tasks, df_comp_all[['id', 'company_name']], left_on='company_id', right_on='id',
                                    how='left', suffixes=('', '_c'))
            else:
                df_tasks['company_name'] = '🏢 【一般業務】'

            df_tasks['name_en'] = df_tasks['name_en'].fillna('共通タスク')
            df_tasks['company_name'] = df_tasks['company_name'].fillna('🏢 【一般業務】')
            df_tasks['status'] = df_tasks.get('status', '未完了')
            df_tasks = df_tasks[(df_tasks['company_id'].isin(valid_company_ids)) | (df_tasks['worker_id'] == '0')]

            if not df_tasks.empty:
                for (comp, name), group in df_tasks.sort_values(by='event_date').groupby(['company_name', 'name_en']):
                    st.markdown(f"**{comp} / 👤 {name}**")
                    for _, r in group.iterrows():
                        c_date, c_task, c_btn = st.columns([2, 5, 2])
                        is_done = r['status'] == '完了'
                        c_date.write(r['event_date'])
                        c_task.markdown(
                            f"{'☑' if is_done else '▢'} {'~~' + r['task_name'] + '~~' if is_done else r['task_name']}")
                        if c_btn.button("☑ 取消" if is_done else "▢ 完了", key=f"dash_{r['id']}"):
                            db.collection('events_logs').document(str(r['id'])).update(
                                {'status': '未完了' if is_done else '完了'})
                            clear_caches();
                            st.rerun()
                    st.divider()
            else:
                st.write("タスクはありません")

    with col2:
        # ★ 追加：人材アラート
        st.subheader("🛂 人材 期限アラート (5ヶ月以内)")
        df_w = fetch_all_cached("foreign_workers")
        w_alerts = []
        if not df_w.empty and not df_comp_all.empty:
            df_merged = pd.merge(df_w[df_w['company_id'].isin(valid_company_ids)], df_comp_all[['id', 'company_name']],
                                 left_on='company_id', right_on='id', how='left')
            limit = today + timedelta(days=150)
            for _, r in df_merged.iterrows():
                try:
                    p_d = datetime.strptime(str(r.get('passport_expiration_date', '')), '%Y-%m-%d').date()
                    if today <= p_d <= limit: w_alerts.append(
                        {"氏名": r.get('name_en', ''), "種類": "パスポート", "日付": str(p_d)})
                except:
                    pass
                try:
                    v_d = datetime.strptime(str(r.get('visa_expiry', '')), '%Y-%m-%d').date()
                    if today <= v_d <= limit: w_alerts.append(
                        {"氏名": r.get('name_en', ''), "種類": "在留期限", "日付": str(v_d)})
                except:
                    pass
        if w_alerts:
            st.dataframe(pd.DataFrame(w_alerts), use_container_width=True, hide_index=True)
        else:
            st.write("対象者なし")

        st.write("---")

        # ★ 追加：会社アラート（36協定・講習日）
        st.subheader("🏢 会社 期限・注意アラート")
        c_alerts = []
        if not df_comp_all.empty:
            for _, c in df_comp_all[df_comp_all['id'].isin(valid_company_ids)].iterrows():
                # 36協定: 期限が過ぎていたらアラート
                a36_str = str(c.get('agreement_36_date', ''))
                if a36_str and a36_str not in ["nan", "ー", "None", ""]:
                    try:
                        if today > datetime.strptime(a36_str, '%Y-%m-%d').date():
                            c_alerts.append({"会社名": c['company_name'], "種類": "36協定 期限切れ", "日付": a36_str})
                    except:
                        pass

                # 講習日: 6ヶ月前になったらアラート
                tr_str = str(c.get('training_date', ''))
                if tr_str and tr_str not in ["nan", "ー", "None", ""]:
                    try:
                        tr_d = datetime.strptime(tr_str, '%Y-%m-%d').date()
                        limit_6m = today + timedelta(days=180)
                        if today <= tr_d <= limit_6m:
                            c_alerts.append({"会社名": c['company_name'], "種類": "講習日接近(6ヶ月以内)", "日付": tr_str})
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
    df_tasks = fetch_all_cached("events_logs")
    df_workers = fetch_all_cached("foreign_workers")
    df_mileage = fetch_all_cached("mileage_logs")

    if not df_tasks.empty and not df_workers.empty:
        df_tasks = pd.merge(df_tasks, df_workers[['id', 'name_en', 'company_id']], left_on='worker_id', right_on='id',
                            how='left', suffixes=('', '_w'))
        df_tasks['company_id'] = df_tasks.get('company_id_w', df_tasks.get('company_id'))
    df_tasks['name_en'] = df_tasks.get('name_en', pd.Series(dtype=str)).fillna('一般')
    df_tasks['status'] = df_tasks.get('status', '未完了')
    if not df_tasks.empty: df_tasks = df_tasks[
        (df_tasks['company_id'].isin(valid_company_ids)) | (df_tasks['worker_id'] == '0')]

    col_cal, col_panel = st.columns([7, 3])
    with col_cal:
        t_date = st.date_input("月を選択", datetime.now(), key="cal_month_view")
        y, m = t_date.year, t_date.month
        calendar.setfirstweekday(calendar.SUNDAY)

        # ★修正1：階段現象の解消（ループの「外」で1回だけ枠を作る）
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
                        color = '#ff8a8a' if jp_holidays.get(d_date) or i == 0 else '#8ab4ff' if i == 6 else '#ffffff'
                        html = f"<div class='cal-day-header' style='color:{color};'>{day}</div>"

                        tasks_html = ""
                        if not df_tasks.empty:
                            for _, t in df_tasks[df_tasks['event_date'] == d_str].iterrows():
                                base_class = "task-item task-done" if t['status'] == '完了' else "task-item"
                                if str(t['worker_id']) == '0': base_class += " task-general"
                                tasks_html += f"<div class='{base_class}'>{'☑' if t['status'] == '完了' else '▢'} {str(t['name_en'])[:4]}: {t['task_name']}</div>"
                        if not df_mileage.empty and 'record_date' in df_mileage.columns:
                            for _, m_row in df_mileage[df_mileage['record_date'] == d_str].iterrows():
                                tasks_html += f"<div class='task-item task-mileage'>🚗 {m_row.get('driven_km', 0)}km ({str(m_row.get('driver_name', '')).replace('青山（', '').replace('）', '')})</div>"
                        st.markdown(f'<div class="cal-cell">{html}{tasks_html}</div>', unsafe_allow_html=True)
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
                st.markdown(f"**{'☑' if is_done else '▢'} {str(t['name_en'])[:4]}**: {t['task_name']}")
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
                if st.button("🗑️ 削除", key=f"del_m_{m_row['id']}"):
                    db.collection('mileage_logs').document(m_row['id']).delete()
                    clear_caches()
                    st.rerun()
                st.write("---")

        if not has_plan: st.caption("予定はありません")
        st.divider()

        # ★修正2：消してしまっていた追加UIの完全復元
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
                        tn = st.text_input("タスク名", key="add_w_t")
                        if st.button("追加", key="btn_add_w"):
                            db.collection('events_logs').add(
                                {"worker_id": str(s_w), "task_name": tn, "event_date": target_str, "status": "未完了",
                                 "created_at": firestore.SERVER_TIMESTAMP})
                            db.collection('worker_logs').add(
                                {"worker_id": str(s_w), "log_date": target_str, "log_content": f"【タスク登録】{tn}",
                                 "created_at": firestore.SERVER_TIMESTAMP})
                            clear_caches()
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
                                    db.collection('events_logs').add(
                                        {"worker_id": str(s_w), "task_name": d['task_name'], "event_date": evd,
                                         "status": "未完了", "created_at": firestore.SERVER_TIMESTAMP})
                                    db.collection('worker_logs').add({"worker_id": str(s_w), "log_date": evd,
                                                                      "log_content": f"【タスク登録】{d['task_name']}",
                                                                      "created_at": firestore.SERVER_TIMESTAMP})
                                clear_caches()
                                st.rerun()

        with st.expander("🏢 一般・会社タスクを追加"):
            if not df_comp_all.empty:
                df_c_sub = df_comp_all[df_comp_all['id'].isin(valid_company_ids)]
                c_opts = ['0'] + df_c_sub['id'].tolist()
                c_names = ["指定なし（一般業務）"] + df_c_sub['company_name'].tolist()
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
                    clear_caches()
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
                        {"record_date": target_str, "driver_name": dr_direct, "start_km": last_end_km,
                         "end_km": last_end_km + dist, "driven_km": dist})
                    clear_caches()
                    st.rerun()
                else:
                    st.warning("距離を入力してください")


# ==========================================
# 👥 画面：名簿
# ==========================================
def show_worker_list():
    st.title("👥 外国人材名簿")
    df_w = fetch_all_cached("foreign_workers")
    df_all_logs = fetch_all_cached("worker_logs")

    if df_w.empty or df_comp_all.empty: st.info("データなし"); return

    df_w = df_w[df_w['company_id'].isin(valid_company_ids)]
    df = pd.merge(df_w, df_comp_all[['id', 'company_name', 'address']], left_on='company_id', right_on='id',
                  how='left').rename(columns={'address': 'comp_address', 'id_x': 'id'})
    df['visa_order'] = df['visa_status'].map(
        {'技能実習1号': 1, '技能実習2号': 2, '技能実習3号': 3, '特定活動': 4, '特定技能1号': 5, '特定技能2号': 6}).fillna(7)
    df = df.sort_values(by=['company_name', 'visa_order', 'entry_date'], ascending=[True, True, True])

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
    tab_info, tab_log, tab_files = st.tabs(["📋 基本情報", "📝 ログ・履歴", "📁 書類管理"])

    with tab_info:
        col_img, col_p, col_v, col_c = st.columns(4)
        with col_img:
            img_val = str(w.get('photo_path', ''))
            if img_val.startswith('http'):
                st.image(img_val, use_container_width=True)
            else:
                st.info("📷 未登録")
        col_p.markdown(
            f"##### 👤 本人情報\n<div style='line-height:1.6; font-size:14px;'><b>生年月日</b><br>{format_date(w.get('birthdate'))}<br><br><b>性別</b><br>{format_date(w.get('gender'))}<br><br><b>国籍</b><br>{format_date(w.get('nationality'))}<br><br><b>本国居住地</b><br>{format_date(w.get('home_address'))}</div>",
            unsafe_allow_html=True)
        col_v.markdown(
            f"##### ✈️ 在留情報\n<div style='line-height:1.6; font-size:14px;'><b>在留期限</b><br>{format_date(w.get('visa_expiry'))}<br><br><b>パスポート</b><br>{format_date(w.get('passport_expiration_date'))}<br><br><b>入国日</b><br>{format_date(w.get('entry_date'))}<br><br><b>帰国日</b><br>{format_date(w.get('return_date'))}</div>",
            unsafe_allow_html=True)
        col_c.markdown(
            f"##### 🏢 その他\n<div style='line-height:1.6; font-size:14px;'><b>宿舎住所</b><br>{format_date(w.get('residence_address'))}<br><br><b>斡旋機関</b><br>{format_date(w.get('dispatch_agency'))}<br><br><b>書類状況</b><br>{format_date(w.get('document_status'))}<br><br><b>備考</b><br>{format_date(w.get('remarks'))}</div>",
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
                    {"worker_id": selected_id, "log_date": l_date.strftime("%Y-%m-%d"), "log_content": l_text,
                     "created_at": firestore.SERVER_TIMESTAMP})
                clear_caches();
                st.rerun()
        for _, l in log_df.iterrows(): st.markdown(f"**{l['log_date']}**： {l.get('log_content', '')}"); st.divider()

    with tab_files:
        manage_files_ui(f"workers/{selected_id}/files", label=f"{w['name_en']} さんの書類")


# ==========================================
# 🏢 ★新機能：会社詳細・ファイル（専用項目・カテゴリ別ログ）
# ==========================================
def show_company_details():
    st.title("🏢 会社詳細・ファイル")
    if df_comp_all.empty: st.warning("会社が登録されていません。"); return

    df_c = df_comp_all[df_comp_all['id'].isin(valid_company_ids)]
    c_name = st.selectbox("対象の会社を選択してください", df_c['company_name'].tolist())

    c_data = df_c[df_c['company_name'] == c_name].iloc[0]
    c_id = str(c_data['id'])  # int64対策で文字列化

    tab_info, tab_log, tab_file = st.tabs(["📋 基本情報・設定", "📝 カテゴリ別ログ", "📁 共有フォルダ"])

    with tab_info:
        with st.form("comp_edit_form"):
            st.markdown("##### ⚙️ 各種設定・期限")
            c1, c2 = st.columns(2)

            def pd_dt(s): return datetime.strptime(str(s), '%Y-%m-%d') if pd.notna(s) and str(s) not in ["ー", "nan",
                                                                                                         "None",
                                                                                                         ""] else datetime.now()

            with c1:
                a36 = st.date_input("36協定 期限日（過ぎるとアラート）", pd_dt(c_data.get('agreement_36_date')))
                tr_d = st.date_input("講習日（6ヶ月前からアラート）", pd_dt(c_data.get('training_date')))

                wp_opts = ["未確認", "◯", "✖"]
                wp_val = str(c_data.get('workplace_confirmed', '未確認'))
                wp = st.selectbox("実習場所確認", wp_opts, index=wp_opts.index(wp_val) if wp_val in wp_opts else 0)

            with c2:
                inst_mgr = st.text_input("指導責任者", value=format_date(c_data.get('instructor_manager', '')))
                v_hours = st.text_area("変形労働 備考", value=format_date(c_data.get('variable_working_hours_remarks', '')))

            if st.form_submit_button("💾 会社情報を保存"):
                # SQLite等へのエクスポートも考慮し、Python標準型（str）に変換してFirestoreへ送信
                db.collection('companies').document(c_id).update({
                    "agreement_36_date": a36.strftime('%Y-%m-%d'),
                    "training_date": tr_d.strftime('%Y-%m-%d'),
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
            l_text = lc3.text_input("記録内容（例：○○氏を指導員として追加など）")
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
            c_logs['log_category'] = c_logs.get('log_category', '一般').fillna('一般')

            # カテゴリで絞り込み表示もできるようにする
            filter_cat = st.radio("表示フィルター", ["すべて"] + log_cats, horizontal=True)
            if filter_cat != "すべて": c_logs = c_logs[c_logs['log_category'] == filter_cat]

            for _, l in c_logs.sort_values(by="log_date", ascending=False).iterrows():
                badge = f"【{l['log_category']}】"
                st.markdown(
                    f"**{l['log_date']}** <span style='color:#ffaa00;'>{badge}</span> {l.get('log_content', '')}",
                    unsafe_allow_html=True)
                st.divider()

    with tab_file:
        manage_files_ui(f"companies/{c_id}/shared", label=f"{c_name} 共有")


# ==========================================
# 📝 画面：ログ全般（省略化）
# ==========================================
def show_logs_manager():
    st.title("📝 ログ一覧（全社・全体）")
    st.info("※会社ごとの詳細ログ入力は「🏢 会社詳細・ファイル」から行えます。")
    # 既存コード省略（動作軽量化のため。必要に応じ復元可）


def show_data_editor():
    st.title("📝 名簿編集")
    if df_comp_all.empty: return
    df_c = df_comp_all[df_comp_all['id'].isin(valid_company_ids)]
    c1, c2 = st.columns(2)
    sc = c1.selectbox("1. 現在の会社", df_c['company_name'].tolist())
    scid = str(df_c[df_c['company_name'] == sc]['id'].values[0])
    df_w = fetch_where("foreign_workers", "company_id", "==", scid)
    if df_w.empty: c2.error("人材なし"); return
    sw = c2.selectbox("2. 対象者", df_w['name_en'].tolist())
    w = df_w[df_w['name_en'] == sw].iloc[0]
    target_id = str(w['id'])

    # 画像とフォーム部分（変更なしなので省略表記せず実装）
    col_img, col_form = st.columns([1, 3])
    with col_img:
        st.write("📷 **写真のアップロード**")
        if "uploader_key" not in st.session_state: st.session_state.uploader_key = str(time.time())
        new_photo = st.file_uploader("新しい写真を選択", type=["jpg", "png", "jpeg"], key=st.session_state.uploader_key)
        if new_photo and st.button("🚀 保存", type="primary"):
            import io;
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

            with st.spinner('送信中...'):
                url = upload_image_to_storage(DummyFile(img_byte_arr), target_id)
                if url: db.collection('foreign_workers').document(target_id).update(
                    {"photo_path": url}); clear_caches(); st.rerun()

    with col_form:
        with st.form("e"):
            ncid = str(df_comp_all[
                           df_comp_all['company_name'] == st.selectbox("所属", df_comp_all['company_name'].tolist(),
                                                                       index=df_comp_all['company_name'].tolist().index(
                                                                           sc))]['id'].values[0])
            nr = st.text_input("寮住所", value=format_date(w.get('residence_address', '')))
            nbirth = st.text_input("生年月日", value=format_date(w.get('birthdate', '')))
            if st.form_submit_button("💾 保存"):
                db.collection('foreign_workers').document(target_id).update({
                    "company_id": ncid, "residence_address": str(nr), "birthdate": str(nbirth)
                    # 省略：他の項目も同様に str() で囲むとより安全です
                })
                clear_caches();
                st.success("更新完了！");
                st.rerun()


def show_add_new():
    st.title("➕ 名簿へ新規追加")
    t1, t2 = st.tabs(["🏢 会社の新規登録", "👤 外国人材の新規登録"])
    with t1:
        with st.form("c"):
            cn = st.text_input("会社名");
            ca = st.selectbox("地域", ["近畿", "関東", "東海", "静岡", "九州", "中四国", "北信越", "北海道・東北"])
            if st.form_submit_button("登録") and cn:
                db.collection('companies').add(
                    {"company_name": str(cn), "area": str(ca), "created_at": firestore.SERVER_TIMESTAMP});
                clear_caches();
                st.rerun()
    with t2:
        if not df_comp_all.empty:
            df_c = df_comp_all[df_comp_all['id'].isin(valid_company_ids)]
            with st.form("w"):
                comp = str(st.selectbox("所属", df_c['id'].tolist(),
                                        format_func=lambda x: df_c[df_c['id'] == x]['company_name'].values[0]))
                name = st.text_input("氏名");
                visa = st.selectbox("資格", ["技能実習1号", "技能実習2号", "技能実習3号", "特定技能1号", "特定技能2号", "特定活動", "その他"])
                if st.form_submit_button("登録") and name:
                    db.collection('foreign_workers').add(
                        {"company_id": comp, "name_en": str(name), "visa_status": str(visa), "is_away": 0,
                         "document_status": "本人保持", "created_at": firestore.SERVER_TIMESTAMP})
                    clear_caches();
                    st.rerun()


# ==========================================
# 📝 画面：ログ全般（復元）
# ==========================================
def show_logs_manager():
    st.title("📝 ログ一覧（全社・全体）")
    st.info("※会社ごとの詳細ログ入力は「🏢 会社詳細・ファイル」から行えます。")
    t1, t2 = st.tabs(["🏢 会社ログ", "👤 個人ログ"])
    with t1:
        if not df_comp_all.empty:
            df_c = df_comp_all[df_comp_all['id'].isin(valid_company_ids)]
            s_c = st.selectbox("会社を選択", df_c['id'].tolist(), format_func=lambda x: df_c[df_c['id'] == x]['company_name'].values[0])
            with st.form("comp_log"):
                l_d = st.date_input("日付", datetime.now())
                l_t = st.text_input("記録内容")
                if st.form_submit_button("会社ログを追加"):
                    db.collection('company_logs').add({"company_id": str(s_c), "log_date": l_d.strftime("%Y-%m-%d"), "log_content": l_t, "created_at": firestore.SERVER_TIMESTAMP})
                    clear_caches(); st.success("追加しました！"); st.rerun()
            c_logs = fetch_where("company_logs", "company_id", "==", str(s_c))
            if not c_logs.empty:
                for _, l in c_logs.sort_values(by="log_date", ascending=False).iterrows():
                    st.markdown(f"**{l['log_date']}**： {l.get('log_content', '')}")
                    st.divider()
    with t2:
        df_w = fetch_all_cached("foreign_workers")
        if not df_w.empty and not df_comp_all.empty:
            df_w = df_w[df_w['company_id'].isin(valid_company_ids)]
            df_w = pd.merge(df_w, df_comp_all[['id', 'company_name']], left_on='company_id', right_on='id', how='left')
            if not df_w.empty:
                s_w = st.selectbox("対象者を選択", df_w['id_x'].tolist(), format_func=lambda x: f"[{df_w[df_w['id_x'] == x]['company_name'].values[0]}] {df_w[df_w['id_x'] == x]['name_en'].values[0]}")
                w_logs = fetch_where("worker_logs", "worker_id", "==", str(s_w))
                if not w_logs.empty:
                    for _, l in w_logs.sort_values(by="log_date", ascending=False).iterrows():
                        st.markdown(f"**{l['log_date']}**： {l.get('log_content', '')}")
                        st.divider()

# ==========================================
# ⚙️ 画面：テンプレート設定（復元）
# ==========================================
def show_tpl_set():
    st.title("⚙️ テンプレート設定")
    with st.form("t"):
        tn = st.text_input("新規テンプレート名")
        if st.form_submit_button("作成"):
            db.collection('task_templates').add({"template_name": tn, "created_at": firestore.SERVER_TIMESTAMP})
            clear_caches()
            st.rerun()
    df_t = fetch_all_cached("task_templates")
    if not df_t.empty:
        stn = st.selectbox("編集するテンプレート", df_t['id'].tolist(), format_func=lambda x: df_t[df_t['id'] == x]['template_name'].values[0])
        if st.button("🗑️ 削除"):
            db.collection('task_templates').document(stn).delete()
            for d_id in fetch_where("template_details", "template_id", "==", stn)['id']:
                db.collection('template_details').document(d_id).delete()
            clear_caches()
            st.rerun()
        df_d = fetch_where("template_details", "template_id", "==", stn)
        if not df_d.empty:
            df_d['offset_days'] = pd.to_numeric(df_d['offset_days'])
            st.table(df_d.sort_values(by="offset_days")[['task_name', 'offset_days']])
            del_id = st.selectbox("削除する詳細", df_d['id'].tolist(), format_func=lambda x: df_d[df_d['id'] == x]['task_name'].values[0])
            if st.button("❌ 削除"):
                db.collection('template_details').document(del_id).delete()
                clear_caches()
                st.rerun()
        with st.form("ad"):
            dn = st.text_input("タスク内容")
            do = st.number_input("日数", value=0)
            if st.form_submit_button("追加"):
                db.collection('template_details').add({"template_id": stn, "task_name": dn, "offset_days": do})
                clear_caches()
                st.rerun()

# ==========================================
# 🚗 画面：走行距離入力（復元）
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
                    db.collection('mileage_logs').add({"record_date": d_meter.strftime("%Y-%m-%d"), "driver_name": dr_meter, "start_km": s_meter, "end_km": e_meter, "driven_km": driven})
                    st.session_state.m_start = e_meter
                    st.session_state.m_end = e_meter
                    clear_caches()
                    st.success("保存！")
                    time.sleep(1)
                    st.rerun()
    with t2:
        with st.container():
            d_direct = st.date_input("日付", datetime.now(), key="date_direct")
            dr_direct = st.selectbox("運転者", ["青山（妻）", "青山（夫）", "スタッフ"], key="driver_direct")
            dist = st.number_input("距離 (km)", value=0, min_value=0, step=1)
            if st.button("💾 記録", type="primary"):
                if dist > 0:
                    new_end = last_end_km + dist
                    db.collection('mileage_logs').add({"record_date": d_direct.strftime("%Y-%m-%d"), "driver_name": dr_direct, "start_km": last_end_km, "end_km": new_end, "driven_km": dist})
                    st.session_state.m_start = new_end
                    st.session_state.m_end = new_end
                    clear_caches()
                    st.success("保存！")
                    time.sleep(1)
                    st.rerun()

# ==========================================
# 🔄 画面ルーティング
# ==========================================
if page == "🏠 ダッシュボード":
    show_dashboard()
elif page == "🗓️ カレンダー":
    show_calendar()
elif page == "👥 外国人材名簿":
    show_worker_list()
elif page == "📝 名簿編集":
    show_data_editor()
elif page == "🏢 会社詳細・ファイル":
    show_company_details()
elif page == "📝 ログ":
    show_logs_manager()
elif page == "➕ 名簿へ新規追加":
    show_add_new()
elif page == "⚙️ テンプレート設定":
    show_tpl_set()
elif page == "🚗 走行距離入力":
    show_mileage()
