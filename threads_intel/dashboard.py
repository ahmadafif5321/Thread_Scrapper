from __future__ import annotations

import asyncio
from datetime import date
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from threads_intel.analytics import (
    best_posting_hours,
    compare_snapshots,
    detect_hook_type,
    engagement_rate,
    hook_reason,
    score_virality,
    summarize,
    total_engagement,
    topic_summary,
    trigger_reason,
    trigger_tags,
)
from threads_intel.ai_analysis import AIAnalysisError, analyze_snapshot, rewrite_hook
from threads_intel.config import DB_PATH
from threads_intel.config import FETCH_TIMEOUT_SECONDS
from threads_intel.fetcher import ThreadsFetchError, fetch_profile
from threads_intel.storage import (
    delete_account,
    latest_snapshot,
    list_usernames,
    new_posts_since_previous,
    recent_fetches,
    save_snapshot,
    snapshot_history,
)


APP_NAME = "Megu Threads Scrape"
GMT8 = ZoneInfo("Asia/Kuala_Lumpur")


st.set_page_config(page_title=APP_NAME, layout="wide")
st.title(APP_NAME)


@st.cache_data(ttl=10)
def load_usernames(db_path: str) -> list[str]:
    return list_usernames(db_path)


@st.cache_data(ttl=10)
def load_latest(username: str, db_path: str):
    return latest_snapshot(username, db_path)


@st.cache_data(ttl=10)
def load_history(username: str, db_path: str) -> pd.DataFrame:
    return pd.DataFrame(snapshot_history(username, db_path))


@st.cache_data(ttl=10)
def load_fetch_logs(db_path: str) -> pd.DataFrame:
    return pd.DataFrame(recent_fetches(db_path=db_path))


@st.cache_data(ttl=10)
def load_new_posts(username: str, db_path: str) -> pd.DataFrame:
    return pd.DataFrame(new_posts_since_previous(username, db_path))


def normalize_usernames(raw: str) -> list[str]:
    names = []
    for item in raw.replace("\n", ",").split(","):
        username = item.strip().lstrip("@").lower()
        if username and username not in names:
            names.append(username)
    return names


def format_gmt8(value: str) -> str:
    if not value:
        return ""
    raw = str(value).strip()
    try:
        if raw.isdigit():
            unit = "ms" if len(raw) > 10 else "s"
            ts = pd.to_datetime(int(raw), unit=unit, utc=True, errors="coerce")
        else:
            ts = pd.to_datetime(raw, utc=True, errors="coerce", format="mixed")
    except (TypeError, ValueError, OverflowError):
        return raw
    if pd.isna(ts):
        return raw
    return ts.tz_convert(GMT8).strftime("%d-%m-%y %H:%M")


def format_frame_times(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    for column in columns:
        if column in out.columns:
            out[column] = out[column].map(format_gmt8)
    return out


def post_row(post, followers: int) -> dict:
    tags = trigger_tags(post.text)
    return {
        "Eng %": engagement_rate(post, followers),
        "Engagement": total_engagement(post),
        "Likes": post.likes,
        "Comments": post.replies,
        "Replies": post.replies,
        "Reposts": post.reposts,
        "Quotes": post.quotes,
        "Reactions": post.reactions,
        "Virality": f"{score_virality(post, followers)}/10",
        "Hook type": detect_hook_type(post.text),
        "Triggers": ", ".join(tags),
        "Posted at": format_gmt8(post.posted_at),
        "Posted raw": post.posted_at,
        "Text": post.text,
        "Link": post.url,
    }


def get_post_by_text(posts, text: str):
    for post in posts:
        if post.text == text:
            return post
    return None


with st.sidebar:
    db_path = st.text_input("SQLite database path", value=DB_PATH)
    known_usernames = load_usernames(db_path)
    default_names = ", ".join(known_usernames[:3] or ["akmalrahim"])
    usernames_raw = st.text_area("Threads usernames", value=default_names, height=90)
    usernames = normalize_usernames(usernames_raw)
    selected_username = st.selectbox("Active account", usernames or known_usernames or ["akmalrahim"])
    limit = st.number_input("Posts to load", min_value=5, max_value=100, value=30, step=5)
    min_likes = st.number_input("Minimum likes", min_value=0, value=0)
    sort_by = st.selectbox("Sort posts by", ["Engagement", "Eng %", "Likes", "Comments", "Reposts", "Quotes", "Text"])
    fetch_all = st.checkbox("Fetch all listed accounts", value=False)

    if st.button("Fetch", type="primary"):
        targets = usernames if fetch_all else [selected_username]
        if not targets:
            st.error("Enter at least one Threads username.")
        else:
            for target in targets:
                try:
                    with st.spinner(f"Fetching @{target}..."):
                        snap = asyncio.run(asyncio.wait_for(fetch_profile(target, limit=int(limit)), timeout=FETCH_TIMEOUT_SECONDS))
                        save_snapshot(snap, db_path)
                    st.success(f"Fetched @{target}: {len(snap.posts)} posts")
                    st.cache_data.clear()
                except TimeoutError:
                    st.error(f"@{target}: fetch timed out after {FETCH_TIMEOUT_SECONDS:g}s. Try again later or increase FETCH_TIMEOUT_SECONDS in .env.")
                except ThreadsFetchError as exc:
                    st.error(f"@{target}: {exc}")
                except Exception as exc:
                    st.exception(exc)

    st.divider()
    delete_target = st.selectbox("Remove account data", known_usernames or [""])
    confirm_delete = st.checkbox("Confirm account removal")
    if st.button("Remove account", disabled=not delete_target or not confirm_delete):
        deleted = delete_account(delete_target, db_path)
        st.cache_data.clear()
        st.success(f"Removed @{delete_target} ({deleted} rows).")
        st.rerun()

snap = load_latest(selected_username, db_path) if selected_username else None
if not snap:
    st.info("Masukkan username dan tekan Fetch.")
    logs = load_fetch_logs(db_path)
    if not logs.empty:
        st.subheader("Fetch logs")
        st.dataframe(format_frame_times(logs, ["fetched_at"]), width="stretch", hide_index=True)
    st.stop()

summary = summarize(snap)
history = load_history(snap.username, db_path)
last_fetched = snap.fetched_at

st.header(f"@{snap.username}")
st.caption(
    f"{summary['followers']:,} followers | {summary['posts_loaded']} posts loaded | "
    f"last fetched at {format_gmt8(last_fetched)} GMT+8"
)
st.caption(f"Requested limit can be up to 100, but actual posts depend on what the public Threads page exposes. This snapshot has {len(snap.posts)} posts.")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Account score", f"{summary['account_score']}/100")
c2.metric("Avg engagement rate", f"{summary['avg_engagement_rate']}%")
c3.metric("Total engagement", f"{summary['total_engagement']:,}")
c4.metric("Posts loaded", f"{summary['posts_loaded']:,}")

c5, c6, c7, c8 = st.columns(4)
c5.metric("Likes", f"{summary['total_likes']:,}")
c6.metric("Comments", f"{summary['total_comments']:,}")
c7.metric("Reposts", f"{summary['total_reposts']:,}")
c8.metric("Quotes", f"{summary['total_quotes']:,}")

with st.expander("Score breakdown", expanded=True):
    s1, s2, s3, s4 = st.columns(4)
    s1.metric("Engagement", f"{summary['score_engagement']}/40")
    s2.metric("Conversation", f"{summary['score_conversation']}/20")
    s3.metric("Consistency", f"{summary['score_consistency']}/20")
    s4.metric("Hook format", f"{summary['score_format']}/20")
    st.write(summary["score_diagnosis"])
    st.caption(f"Top topic: {summary['top_topic']} | Best time: {summary['best_time']}")

if len(known_usernames) > 1:
    compare = [latest_snapshot(name, db_path) for name in known_usernames]
    compare = [snapshot for snapshot in compare if snapshot]
    if compare:
        st.subheader("Account comparison")
        st.dataframe(pd.DataFrame(compare_snapshots(compare)), width="stretch", hide_index=True)

if not history.empty:
    history["fetched_at"] = pd.to_datetime(history["fetched_at"], errors="coerce")
    history = history.dropna(subset=["fetched_at"])

if not history.empty:
    min_date = history["fetched_at"].min().date()
    max_date = history["fetched_at"].max().date()
    selected_range = st.date_input("Snapshot date range", value=(min_date, max_date))
    if isinstance(selected_range, tuple) and len(selected_range) == 2:
        start_date, end_date = selected_range
    else:
        start_date, end_date = min_date, max_date
    mask = history["fetched_at"].dt.date.between(start_date, end_date)
    filtered_history = history[mask]

    st.subheader("Account history")
    st.line_chart(
        filtered_history.set_index("fetched_at")[["followers", "top_reactions", "posts_loaded"]],
        height=260,
    )
    st.download_button(
        "Download account history CSV",
        format_frame_times(filtered_history, ["fetched_at"]).to_csv(index=False).encode("utf-8"),
        file_name=f"{snap.username}_history.csv",
        mime="text/csv",
    )
else:
    start_date = date.min
    end_date = date.max

posts = [post for post in snap.posts if post.likes >= min_likes]
df = pd.DataFrame([post_row(post, snap.followers) for post in posts])
if not df.empty:
    posted_at = pd.to_datetime(df["Posted raw"], errors="coerce", format="mixed", utc=True)
    start_ts = pd.Timestamp(start_date, tz="UTC")
    end_ts = pd.Timestamp(end_date, tz="UTC") + pd.Timedelta(days=1)
    df["Posted date"] = posted_at.dt.date
    df = df[posted_at.isna() | ((posted_at >= start_ts) & (posted_at < end_ts))]
    visible_text = set(df["Text"].tolist())
    posts = [post for post in posts if post.text in visible_text]
    if sort_by in df.columns:
        descending = sort_by != "Text"
        df = df.sort_values(sort_by, ascending=not descending)
        posts = sorted(posts, key=lambda post: post_row(post, snap.followers)[sort_by], reverse=descending)

new_df = load_new_posts(snap.username, db_path)
if not new_df.empty:
    st.subheader(f"New since previous fetch ({len(new_df)})")
    st.dataframe(format_frame_times(new_df, ["posted_at"]), width="stretch", hide_index=True)

topics = pd.DataFrame(topic_summary(posts))
hours = pd.DataFrame(best_posting_hours(posts))
if not topics.empty or not hours.empty:
    t1, t2 = st.columns(2)
    with t1:
        st.subheader("Topic clusters")
        if topics.empty:
            st.info("No topic data yet.")
        else:
            st.dataframe(topics, width="stretch", hide_index=True)
    with t2:
        st.subheader("Best posting time")
        if hours.empty:
            st.info("Not enough reliable post timestamps yet.")
        else:
            st.dataframe(hours, width="stretch", hide_index=True)

st.subheader(f"Top hooks ({min(10, len(posts))})")
for post in sorted(posts, key=lambda item: engagement_rate(item, snap.followers), reverse=True)[:10]:
    er = engagement_rate(post, snap.followers)
    with st.expander(f"{er}% ER | {total_engagement(post)} engagement | {post.text[:90]}"):
        a, b, c, d = st.columns(4)
        a.metric("Virality", f"{score_virality(post, snap.followers)}/10")
        b.metric("Likes", f"{post.likes:,}")
        c.metric("Comments", f"{post.replies:,}")
        d.metric("Reposts + Quotes", f"{post.reposts + post.quotes:,}")
        h1, h2 = st.columns([1, 2])
        h1.write("**Hook type**")
        h1.write(detect_hook_type(post.text))
        h2.write("**Why this hook type**")
        h2.write(hook_reason(post.text))
        tags = trigger_tags(post.text)
        st.write("**Triggers**")
        st.write(" | ".join(tags))
        st.caption("Trigger basis: " + " ".join(f"{tag}: {trigger_reason(tag)}" for tag in tags))
        st.write("**Analysis**")
        if post.replies > post.likes:
            st.write("This post is conversation-led. It may be useful for building community discussion.")
        elif post.likes and post.replies == 0:
            st.write("This post gets lightweight approval but weak conversation. Add a clearer question or opinion prompt.")
        elif total_engagement(post) == 0:
            st.write("No visible engagement was parsed. Test a sharper first line, stronger specificity, or clearer audience pain.")
        else:
            st.write("This post has visible engagement. Compare its hook, topic, and format against lower-performing posts.")
        if post.url:
            st.link_button("Open post", post.url)

st.subheader(f"All posts ({len(df)})")
if df.empty:
    st.warning("No posts match the current filters.")
else:
    visible_df = df.drop(columns=["Posted raw"], errors="ignore")
    st.download_button(
        "Download CSV",
        visible_df.to_csv(index=False).encode("utf-8"),
        file_name=f"{snap.username}_posts.csv",
        mime="text/csv",
    )
    st.dataframe(visible_df, width="stretch", hide_index=True)

with st.expander("AI analysis and hook rewrite"):
    st.caption("Optional. Requires OPENAI_API_KEY in .env.")
    if st.button("Generate AI account analysis"):
        try:
            with st.spinner("Generating AI analysis..."):
                st.write(analyze_snapshot(snap))
        except AIAnalysisError as exc:
            st.warning(str(exc))
        except Exception as exc:
            st.error(f"AI analysis failed: {exc}")
    if posts:
        selected_text = st.selectbox("Post to rewrite", [post.text[:140] for post in posts])
        selected_post = next((post for post in posts if post.text.startswith(selected_text)), posts[0])
        if st.button("Rewrite hook ideas"):
            try:
                with st.spinner("Rewriting hook..."):
                    st.write(rewrite_hook(selected_post.text))
            except AIAnalysisError as exc:
                st.warning(str(exc))
            except Exception as exc:
                st.error(f"Hook rewrite failed: {exc}")

logs = load_fetch_logs(db_path)
if not logs.empty:
    st.subheader("Fetch logs")
    st.dataframe(format_frame_times(logs, ["fetched_at"]), width="stretch", hide_index=True)

with st.expander("How the analysis works"):
    st.write("Engagement = likes + comments/replies + reposts + quotes.")
    st.write("Engagement rate = engagement divided by followers, shown as a percentage.")
    st.write("Hook type is rule-based from keywords and text patterns, not AI judgment yet.")
    st.write("Account score combines average engagement rate, conversation ratio, consistency of posts getting engagement, and hook/format signals.")
