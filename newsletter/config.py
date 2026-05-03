import os

RECIPIENT_EMAIL = os.environ.get("RECIPIENT_EMAIL", "")
SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "")
SUBSTACK_URL = os.environ.get("SUBSTACK_URL", "")  # e.g. "https://morningaibrief.substack.com"

MAX_ARTICLES_PER_TOPIC = 3
SNIPPET_MAX_CHARS = 300
DAYS_LOOKBACK = 1

TOPIC_COLORS: dict[str, str] = {
    "AI & Data Tools":     "#4F46E5",  # indigo
    "AI in Finance":       "#059669",  # emerald
    "AI in Sports":        "#DC2626",  # red
    "Research & Academia": "#7C3AED",  # violet
    "Podcasts":            "#D97706",  # amber
}

# Emoji icons — used in Substack HTML and Telegram posts
TOPIC_ICONS: dict[str, str] = {
    "AI & Data Tools":     "📊",
    "AI in Finance":       "📈",
    "AI in Sports":        "🏃",
    "Research & Academia": "📚",
    "Podcasts":            "🎧",
}

# Keywords used to score relevance within each topic section
TOPIC_KEYWORDS: dict[str, list[str]] = {
    "AI & Data Tools": [
        "machine learning", "ai", "llm", "python", "data", "analytics",
        "model", "tool", "framework", "sql", "pipeline", "automation",
        "agent", "gpt", "claude", "embedding", "vector", "transformer",
        "open source", "inference", "fine-tuning", "rag", "multimodal",
        "benchmark", "deployment", "mlops", "gpu", "language model",
    ],
    "AI in Finance": [
        "finance", "financial", "trading", "market", "investment", "fintech",
        "stock", "portfolio", "risk", "banking", "ai", "forecast", "quant",
        "economic", "fund", "crypto", "regulation", "algorithmic", "hedge",
        "systematic", "factor", "alpha", "equity", "derivatives", "macro",
    ],
    "AI in Sports": [
        "sport", "athlete", "performance", "training", "fitness", "wearable",
        "tracking", "analytics", "coaching", "biomechanics", "injury",
        "recovery", "health", "physical", "soccer", "football", "running",
        "endurance", "cycling", "swimming", "heart rate", "vo2", "lactate",
        "strength", "load", "fatigue", "sleep", "nutrition", "physiology",
    ],
    "Research & Academia": [
        "research", "paper", "study", "arxiv", "model", "benchmark",
        "neural", "architecture", "training", "dataset", "safety",
        "alignment", "interpretability", "evaluation", "science",
        "preprint", "peer-reviewed", "experiment", "hypothesis", "findings",
        "reasoning", "multimodal", "emergent", "scaling", "rlhf",
    ],
}

TOPICS: dict[str, list[str]] = {
    "AI & Data Tools": [
        # Established tech publications
        "https://towardsdatascience.com/feed",
        "https://www.technologyreview.com/feed/",
        "https://www.wired.com/feed/rss",
        "https://feeds.feedburner.com/oreilly/radar/atom",
        "https://the-decoder.com/feed/",
        # AI labs & company blogs (verified accessible)
        "https://blog.google/technology/ai/rss/",
        "https://blogs.microsoft.com/ai/feed/",
        "https://deepmind.google/blog/rss.xml",
        "https://engineering.fb.com/feed/",
        # Independent researchers & practitioners
        "https://simonwillison.net/atom/everything/",
        "https://www.interconnects.ai/feed",
        "https://www.oneusefulthing.org/feed",
        "https://magazine.sebastianraschka.com/feed",
        "https://eugeneyan.com/rss/",
        "https://thegradient.pub/rss/",
        # Community & tools
        "https://huggingface.co/blog/feed.xml",
        "https://hnrss.org/best?q=AI+machine+learning",
        "https://hnrss.org/best?q=LLM+agent+tool",
        "https://www.marktechpost.com/feed/",
        "https://machinelearningmastery.com/blog/feed/",
        "https://www.kdnuggets.com/feed",
        "https://wandb.ai/fully-connected/rss.xml",
        "https://paperswithcode.com/latest/rss",
        "https://www.fast.ai/index.xml",
        "https://bair.berkeley.edu/blog/feed.xml",
    ],
    "AI in Finance": [
        # Major news outlets
        "https://feeds.bloomberg.com/technology/news.rss",
        "https://www.cnbc.com/id/100003114/device/rss/rss.html",
        "https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml",
        # Fintech & AI in banking
        "https://www.finextra.com/rss/headlines.aspx",
        # Quant, systematic & algo trading
        "https://alphaarchitect.com/feed/",
        "https://quantpedia.com/blog/feed/",
        "https://hnrss.org/best?q=quantitative+finance+AI",
        "https://hnrss.org/best?q=algorithmic+trading",
        "https://hnrss.org/best?q=fintech+AI",
        # Macro & markets
        "https://abnormalreturns.com/feed/",
        "https://www.capitalspectator.com/feed/",
        "https://feeds.feedburner.com/marginalrevolution/feed",
        "https://blogs.cfainstitute.org/investor/feed/",
    ],
    "AI in Sports": [
        # Sports tech media
        "https://www.sportspromedia.com/feed/",
        "https://sporttechie.com/feed/",
        "https://www.wearable-technologies.com/feed/",
        "https://hnrss.org/best?q=sports+analytics+AI",
        "https://hnrss.org/best?q=wearable+athlete+performance",
        # Major sports outlets (filtered by keywords)
        "https://www.espn.com/espn/rss/news",
        "https://theathletic.com/rss/news/",
        "https://www.frontiersin.org/journals/sports-and-active-living/rss",
        # Endurance & performance science
        "https://www.trainingpeaks.com/blog/feed/",
        "https://www.runnersworld.com/rss/all.xml/",
        "https://www.outsideonline.com/feed/",
        "https://www.scienceofrunning.com/feed/",
        # Academic sports science
        "https://bjsm.bmj.com/rss/current.xml",
        "https://journals.humankinetics.com/rss/journals/ijspp",
        "https://www.tandfonline.com/feed/rss/rjsp20",
        # The Conversation — exercise & sport
        "https://theconversation.com/sport/articles.atom",
    ],
    "Research & Academia": [
        # arXiv — core ML tracks
        "https://arxiv.org/rss/cs.AI",
        "https://arxiv.org/rss/cs.LG",
        "https://arxiv.org/rss/cs.CL",    # NLP / language models
        "https://arxiv.org/rss/cs.CV",    # computer vision
        "https://arxiv.org/rss/cs.RO",    # robotics
        "https://arxiv.org/rss/stat.ML",  # statistical ML
        # Science journalism
        "https://www.quantamagazine.org/feed/",
        "https://theconversation.com/technology/articles.atom",
        "https://news.mit.edu/rss/topic/artificial-intelligence2",
        "https://hai.stanford.edu/news/rss.xml",
        # Lab & institute blogs
        "https://www.deeplearning.ai/the-batch/feed/",
        "https://research.google/blog/rss/",
        "https://www.microsoft.com/en-us/research/feed/",
        # Safety, alignment & policy
        "https://www.alignmentforum.org/feed.xml",
        "https://hnrss.org/best?q=AI+safety+alignment",
        "https://hnrss.org/best?q=LLM+research+paper",
        "https://hnrss.org/best?q=neural+network+benchmark",
        # Papers index
        "https://paperswithcode.com/latest/rss",
        "https://distill.pub/rss.xml",
    ],
    "Podcasts": [
        # Long-form interviews
        "https://lexfridman.com/feed/podcast/",
        "https://www.dwarkeshpatel.com/podcast?format=rss",
        # AI strategy & industry
        "https://feeds.simplecast.com/ORdGvPNL",   # No Priors (a16z)
        "https://feeds.transistor.fm/the-cognitive-revolution",
        # Technical ML
        "https://changelog.com/practicalai/feed",
        "https://twimlai.com/feed/",
        "https://feeds.feedburner.com/TalkingMachines",
        "https://feeds.simplecast.com/54nAGcIl",    # NVIDIA AI Podcast
        # Research / safety / policy
        "https://futureoflife.org/podcast/feed/",
        "https://80000hours.org/podcast/feed.xml",
        # Performance science & decision-making
        "https://feeds.megaphone.fm/hubermanlab",
        "https://fs.blog/knowledge-project/feed/",
        # Neuroscience & science
        "https://braininspired.co/feed/podcast/",
        "https://www.preposterousuniverse.com/podcast/feed/",
        "https://dataskeptic.com/feed.rss",
    ],
}

PODCAST_DAYS_LOOKBACK = 7
MAX_PODCASTS = 1

# Topic rotation by weekday (Monday=0 … Sunday=6).
# "AI & Data Tools" and "Podcasts" run every day.
# Finance: Mon, Fri, weekends | Sports: Tue, Thu, weekends | Research: Wed, weekends
TOPIC_ROTATION: dict[int, list[str]] = {
    0: ["AI & Data Tools", "AI in Finance", "Podcasts"],
    1: ["AI & Data Tools", "AI in Sports", "Podcasts"],
    2: ["AI & Data Tools", "Research & Academia", "Podcasts"],
    3: ["AI & Data Tools", "AI in Sports", "Podcasts"],
    4: ["AI & Data Tools", "AI in Finance", "Podcasts"],
    5: ["AI & Data Tools", "AI in Finance", "AI in Sports", "Research & Academia", "Podcasts"],
    6: ["AI & Data Tools", "AI in Finance", "AI in Sports", "Research & Academia", "Podcasts"],
}
