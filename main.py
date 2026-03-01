import feedparser
import os
import json
from google import genai
from google.genai import types
import firebase_admin
from firebase_admin import credentials, firestore
from newspaper import Article

# 1. Setup AI & Database
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
cred_json = json.loads(os.environ["FIREBASE_CREDENTIALS"])
cred = credentials.Certificate(cred_json)
if not firebase_admin._apps:
    firebase_admin.initialize_app(cred)
db = firestore.client()

# 2. 15+ Global News Sources
SOURCES = [
    {"name": "BBC World", "url": "http://feeds.bbci.co.uk/news/world/rss.xml", "tag": "World"},
    {"name": "Reuters World", "url": "http://feeds.reuters.com/Reuters/worldNews", "tag": "World"},
    {"name": "CNN Top Stories", "url": "http://rss.cnn.com/rss/edition.rss", "tag": "Politics"},
    {"name": "France 24", "url": "https://www.france24.com/en/rss", "tag": "World"},
    {"name": "Al Jazeera", "url": "https://www.aljazeera.com/xml/rss/all.xml", "tag": "Politics"},
    {"name": "The Times", "url": "https://www.thetimes.co.uk/?service=rss", "tag": "World"},
    {"name": "NYT Home", "url": "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml", "tag": "Politics"},
    {"name": "TechCrunch", "url": "https://techcrunch.com/feed/", "tag": "Tech"},
    {"name": "Wired", "url": "https://www.wired.com/feed/rss", "tag": "Tech"},
    {"name": "Nature Research", "url": "https://www.nature.com/nature.rss", "tag": "Research"},
    {"name": "Science Daily", "url": "https://www.sciencedaily.com/rss/all.xml", "tag": "Research"},
    {"name": "ESPN Sports", "url": "https://www.espn.com/espn/rss/news", "tag": "Sports"},
    {"name": "BBC Sport", "url": "http://feeds.bbci.co.uk/sport/rss.xml", "tag": "Sports"},
    {"name": "News 1st", "url": "https://www.newsfirst.lk/feed/", "tag": "Local"},
    {"name": "The Guardian", "url": "https://www.theguardian.com/world/rss", "tag": "World"}
]

def get_full_text(url):
    try:
        article = Article(url)
        article.download()
        article.parse()
        return article.text[:3000] # Give AI first 3000 chars to save tokens
    except:
        return None

def process_news():
    for source in SOURCES:
        feed = feedparser.parse(source['url'])
        for entry in feed.entries[:2]: # Take top 2 from each source
            title = entry.title
            
            # Check for duplicates
            if db.collection("articles").where("title", "==", title).get():
                continue

            full_text = get_full_text(entry.link) or entry.description
            
            prompt = f"""
            Analyze this news article:
            Title: {title}
            Content: {full_text}
            
            1. Summarize in 2 sentences.
            2. Score liability (0=neutral, 100=extreme bias/fake).
            3. Pick the best category from [World, Politics, Tech, Sports, Research].
            
            Return JSON: {{"summary": "...", "score": 0, "category": "..."}}
            """
            
            try:
                response = client.models.generate_content(
                    model="gemini-2.0-flash", 
                    contents=prompt,
                    config=types.GenerateContentConfig(response_mime_type="application/json")
                )
                res = json.loads(response.text)

                db.collection("articles").add({
                    "title": title,
                    "summary": res['summary'],
                    "liability_score": res['score'],
                    "tag": res['category'] or source['tag'],
                    "link": entry.link,
                    "agree_votes": 0,
                    "disagree_votes": 0,
                    "timestamp": firestore.SERVER_TIMESTAMP
                })
                print(f"Success: {title}")
            except Exception as e:
                print(f"Error processing {title}: {e}")

if __name__ == "__main__":
    process_news()
