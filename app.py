"""
app.py — Brand Template Generator (Cloud version)
Uses Supabase for brand storage and logo files.
Set environment variables:
  SUPABASE_URL  = https://xxxx.supabase.co
  SUPABASE_KEY  = your service_role key
Run locally: python3 app.py
Deploy:      Render (connect GitHub repo, set env vars)
"""

from flask import Flask, request, jsonify, render_template_string, send_file
from PIL import Image
import json, os, io, base64, uuid
from generator import build_layout, FORMATS

app = Flask(__name__)

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
USE_SUPABASE = bool(SUPABASE_URL and SUPABASE_KEY)

# Local fallback (for running without Supabase)
BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
BRANDS_FILE = os.path.join(BASE_DIR, "brands_data.json")
UPLOADS_DIR = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOADS_DIR, exist_ok=True)

DEMO_BRAND = {
    "id": "demo_bloom",
    "name": "Bloom Studio",
    "tagline": "Skincare that listens.",
    "industry": "Skincare / Wellness",
    "audience": "Women 25–40 interested in clean beauty",
    "tone": "Warm / Approachable",
    "colors": {"primary": "#C9856A", "secondary": "#F5EAE0", "accent": "#7A9E7E", "background": "#FDFAF7", "text": "#2C2C2C"},
    "fonts": {"heading": "Playfair Display", "body": "Lato"},
    "contentTypes": ["Quote / Inspirational", "Product showcase", "Educational tip", "Testimonial / Review"],
    "cta": "Shop now",
    "handle": "@bloomstudio",
}

# ── Supabase client (lazy init) ───────────────────────────────────────────────

_sb = None

def get_supabase():
    global _sb
    if _sb is None and USE_SUPABASE:
        from supabase import create_client
        _sb = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _sb


# ── Brand storage (Supabase or local) ────────────────────────────────────────

def load_brands():
    sb = get_supabase()
    if sb:
        try:
            res = sb.table("brands").select("*").order("created_at").execute()
            brands = [row["data"] for row in res.data]
            return brands if brands else [DEMO_BRAND]
        except Exception as e:
            print(f"Supabase load error: {e}")

    # Local fallback
    if not os.path.exists(BRANDS_FILE):
        return [DEMO_BRAND]
    try:
        with open(BRANDS_FILE) as f:
            brands = json.load(f)
        return brands if brands else [DEMO_BRAND]
    except Exception:
        return [DEMO_BRAND]


def save_brand_to_db(brand):
    sb = get_supabase()
    if sb:
        try:
            sb.table("brands").upsert({"id": brand["id"], "data": brand}).execute()
            return
        except Exception as e:
            print(f"Supabase save error: {e}")

    # Local fallback
    brands = load_brands()
    brands = [b for b in brands if b["id"] != brand["id"]]
    brands.append(brand)
    with open(BRANDS_FILE, "w") as f:
        json.dump(brands, f, indent=2)


def delete_brand_from_db(brand_id):
    sb = get_supabase()
    if sb:
        try:
            sb.table("brands").delete().eq("id", brand_id).execute()
            # Also delete logo from storage
            try:
                sb.storage.from_("logos").remove([f"{brand_id}.png"])
            except Exception:
                pass
            return
        except Exception as e:
            print(f"Supabase delete error: {e}")

    # Local fallback
    brands = [b for b in load_brands() if b["id"] != brand_id]
    with open(BRANDS_FILE, "w") as f:
        json.dump(brands, f, indent=2)
    logo_path = os.path.join(UPLOADS_DIR, f"{brand_id}_logo.png")
    if os.path.exists(logo_path):
        os.remove(logo_path)


def get_logo(brand_id):
    sb = get_supabase()
    if sb:
        try:
            data = sb.storage.from_("logos").download(f"{brand_id}.png")
            if data:
                return Image.open(io.BytesIO(data)).convert("RGBA")
        except Exception:
            pass

    # Local fallback
    logo_path = os.path.join(UPLOADS_DIR, f"{brand_id}_logo.png")
    if os.path.exists(logo_path):
        try:
            return Image.open(logo_path).convert("RGBA")
        except Exception:
            pass
    return None


def save_logo(brand_id, file_stream):
    img = Image.open(file_stream).convert("RGBA")
    sb = get_supabase()
    if sb:
        try:
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            buf.seek(0)
            sb.storage.from_("logos").upload(
                f"{brand_id}.png", buf.read(),
                {"content-type": "image/png", "upsert": "true"}
            )
            return
        except Exception as e:
            print(f"Supabase logo upload error: {e}")

    # Local fallback
    path = os.path.join(UPLOADS_DIR, f"{brand_id}_logo.png")
    img.save(path)


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template_string(HTML)

@app.route("/api/brands", methods=["GET"])
def get_brands():
    return jsonify(load_brands())

@app.route("/api/brands", methods=["POST"])
def add_brand():
    brand = request.json
    brand["id"] = "brand_" + uuid.uuid4().hex[:8]
    save_brand_to_db(brand)
    return jsonify(brand)

@app.route("/api/brands/<brand_id>", methods=["DELETE"])
def delete_brand(brand_id):
    delete_brand_from_db(brand_id)
    return jsonify({"ok": True})

@app.route("/api/generate", methods=["POST"])
def generate():
    data         = request.json
    brand_id     = data.get("brandId")
    fmt_key      = data.get("format")
    headline     = data.get("headline", "")
    subtext      = data.get("subtext", "")
    cta_text     = data.get("cta", "")
    content_type = data.get("contentType", "")

    brands = load_brands()
    brand = next((b for b in brands if b["id"] == brand_id), None)
    if not brand:
        return jsonify({"error": "Brand not found"}), 404

    logo_img = get_logo(brand_id)
    img = build_layout(brand, fmt_key, headline, subtext, cta_text, content_type, logo_img)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return jsonify({"image": base64.b64encode(buf.getvalue()).decode(), "format": fmt_key})

@app.route("/api/download", methods=["POST"])
def download():
    data         = request.json
    brand_id     = data.get("brandId")
    fmt_key      = data.get("format", "ig_square")
    headline     = data.get("headline", "")
    subtext      = data.get("subtext", "")
    cta_text     = data.get("cta", "")
    content_type = data.get("contentType", "")

    brands = load_brands()
    brand = next((b for b in brands if b["id"] == brand_id), None)
    if not brand:
        return jsonify({"error": "Brand not found"}), 404

    logo_img = get_logo(brand_id)
    img = build_layout(brand, fmt_key, headline, subtext, cta_text, content_type, logo_img)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    fname = brand["name"].lower().replace(" ", "_") + "_" + fmt_key + ".png"
    return send_file(buf, mimetype="image/png", as_attachment=True, download_name=fname)

@app.route("/api/upload-logo/<brand_id>", methods=["POST"])
def upload_logo(brand_id):
    if "logo" not in request.files:
        return jsonify({"error": "No file"}), 400
    try:
        save_logo(brand_id, request.files["logo"])
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


# ── HTML UI (identical to local version) ─────────────────────────────────────

HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Brand Image Generator</title>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#F7F6F3;--surface:#fff;--border:#E5E3DE;
  --text:#1A1916;--muted:#8A8780;
  --r:12px;--shadow:0 1px 4px rgba(0,0,0,.08),0 4px 16px rgba(0,0,0,.04);
}
body{font-family:system-ui,-apple-system,sans-serif;background:var(--bg);color:var(--text);min-height:100vh}
.header{background:var(--surface);border-bottom:1px solid var(--border);padding:0 28px;height:58px;display:flex;align-items:center;justify-content:space-between;position:sticky;top:0;z-index:100}
.logo{font-weight:700;font-size:.95rem;letter-spacing:-.02em}
.logo span{opacity:.35}
.main{max-width:1100px;margin:0 auto;padding:36px 20px 80px;display:grid;grid-template-columns:340px 1fr;gap:28px;align-items:start}
@media(max-width:780px){.main{grid-template-columns:1fr}}
.card{background:var(--surface);border:1px solid var(--border);border-radius:var(--r);overflow:hidden}
.card-pad{padding:20px}
.section-label{font-size:.68rem;font-weight:600;text-transform:uppercase;letter-spacing:.1em;color:var(--muted);margin-bottom:12px}
.brand-list{display:flex;flex-direction:column;gap:8px;margin-bottom:12px}
.brand-item{display:flex;align-items:center;gap:10px;padding:10px 12px;border:1.5px solid var(--border);border-radius:8px;cursor:pointer;transition:all .15s}
.brand-item:hover{border-color:var(--text)}
.brand-item.active{border-color:var(--text);background:var(--bg)}
.brand-dot{width:22px;height:22px;border-radius:50%;flex-shrink:0}
.brand-name{font-size:.85rem;font-weight:500;flex:1}
.brand-del{font-size:.75rem;color:var(--muted);cursor:pointer;padding:2px 6px;border-radius:4px}
.brand-del:hover{color:#c0392b;background:#fdf0f0}
.fmt-grid{display:grid;grid-template-columns:repeat(5,1fr);gap:8px;margin-bottom:20px}
.fmt-card{border:1.5px solid var(--border);border-radius:8px;padding:10px 6px;text-align:center;cursor:pointer;transition:all .15s}
.fmt-card:hover{border-color:var(--text)}
.fmt-card.active{border-color:var(--text);background:var(--bg)}
.fmt-vis{margin:0 auto 6px;border:2px solid currentColor;border-radius:3px;opacity:.4}
.fmt-card.active .fmt-vis{opacity:1}
.fmt-label{font-size:.65rem;font-weight:500;color:var(--muted);line-height:1.3}
.fmt-card.active .fmt-label{color:var(--text)}
.field{margin-bottom:14px}
.field label{display:block;font-size:.78rem;font-weight:500;margin-bottom:5px}
.field input,.field select,.field textarea{width:100%;padding:9px 11px;border:1px solid var(--border);border-radius:8px;font-size:.85rem;font-family:inherit;background:var(--surface);color:var(--text);transition:border-color .15s}
.field input:focus,.field select:focus,.field textarea:focus{outline:none;border-color:var(--text)}
.field-row{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.ct-grid{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:16px}
.ct-pill{padding:5px 12px;border:1.5px solid var(--border);border-radius:20px;font-size:.78rem;cursor:pointer;transition:all .15s;user-select:none}
.ct-pill:hover{border-color:var(--text)}
.ct-pill.active{background:var(--text);color:#fff;border-color:var(--text)}
.btn{display:inline-flex;align-items:center;gap:6px;padding:9px 18px;border-radius:8px;font-size:.875rem;font-weight:500;cursor:pointer;border:none;transition:all .15s;font-family:inherit}
.btn-primary{background:var(--text);color:#fff;width:100%;justify-content:center}
.btn-primary:hover{background:#333}
.btn-primary:disabled{opacity:.35;cursor:not-allowed}
.btn-secondary{background:transparent;color:var(--text);border:1px solid var(--border)}
.btn-secondary:hover{background:var(--bg)}
.btn-sm{padding:6px 14px;font-size:.8rem}
.preview-panel{position:sticky;top:80px}
.preview-box{background:#e8e6e1;border-radius:var(--r);display:flex;align-items:center;justify-content:center;min-height:400px;position:relative;overflow:hidden}
.preview-img{max-width:100%;max-height:600px;border-radius:8px;box-shadow:var(--shadow);display:none}
.preview-placeholder{text-align:center;color:var(--muted);padding:40px}
.preview-placeholder-icon{font-size:2.5rem;margin-bottom:12px;opacity:.4}
.preview-placeholder p{font-size:.85rem}
.preview-actions{display:flex;gap:10px;padding:14px 20px}
.preview-actions .btn{flex:1;justify-content:center}
.loading-overlay{position:absolute;inset:0;background:rgba(247,246,243,.85);display:none;align-items:center;justify-content:center;flex-direction:column;gap:12px;font-size:.85rem;color:var(--muted)}
.spinner{width:32px;height:32px;border:3px solid var(--border);border-top-color:var(--text);border-radius:50%;animation:spin .8s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
.modal-overlay{position:fixed;inset:0;background:rgba(0,0,0,.4);z-index:200;display:none;align-items:center;justify-content:center;padding:20px}
.modal-overlay.open{display:flex}
.modal{background:var(--surface);border-radius:16px;max-width:560px;width:100%;max-height:90vh;overflow-y:auto}
.modal-header{padding:20px 24px 16px;border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between}
.modal-title{font-size:1rem;font-weight:600}
.modal-close{background:none;border:none;font-size:1.2rem;cursor:pointer;color:var(--muted);padding:4px}
.modal-body{padding:20px 24px}
.modal-footer{padding:16px 24px;border-top:1px solid var(--border);display:flex;gap:10px;justify-content:flex-end}
.fsec{font-size:.68rem;font-weight:600;text-transform:uppercase;letter-spacing:.1em;color:var(--muted);margin:20px 0 10px;padding-bottom:6px;border-bottom:1px solid var(--border)}
.color-field{display:flex;gap:8px;align-items:center}
.color-field input[type=color]{width:38px;height:36px;padding:2px;border-radius:6px;border:1px solid var(--border);cursor:pointer;background:none;flex-shrink:0}
.color-field input[type=text]{flex:1}
.tone-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:6px}
.tone-opt{padding:8px 12px;border:1.5px solid var(--border);border-radius:8px;cursor:pointer;font-size:.8rem;transition:all .15s;text-align:center}
.tone-opt:hover{border-color:var(--text)}
.tone-opt.selected{background:var(--text);color:#fff;border-color:var(--text)}
.hint-box{margin-top:16px}
.hint-card{background:var(--surface);border:1px solid var(--border);border-radius:var(--r);padding:16px 20px;font-size:.82rem;color:var(--muted);line-height:1.7}
.toast{position:fixed;bottom:24px;right:24px;background:var(--text);color:#fff;padding:10px 18px;border-radius:8px;font-size:.85rem;z-index:300;opacity:0;transition:opacity .3s;pointer-events:none}
.toast.show{opacity:1}
</style>
</head>
<body>
<div class="header">
  <div class="logo">Brand Generator <span>/ Nonprofit</span></div>
  <button class="btn btn-secondary btn-sm" onclick="openModal()">+ Add brand</button>
</div>
<div class="main">
  <div>
    <div class="card card-pad" style="margin-bottom:16px">
      <div class="section-label">Brand</div>
      <div class="brand-list" id="brandList"></div>
    </div>
    <div class="card card-pad" style="margin-bottom:16px">
      <div class="section-label">Format</div>
      <div class="fmt-grid">
        <div class="fmt-card active" data-fmt="ig_square" onclick="selectFmt(this)"><div class="fmt-vis" style="width:28px;height:28px"></div><div class="fmt-label">Instagram<br>Square</div></div>
        <div class="fmt-card" data-fmt="ig_portrait" onclick="selectFmt(this)"><div class="fmt-vis" style="width:24px;height:30px"></div><div class="fmt-label">Instagram<br>Portrait</div></div>
        <div class="fmt-card" data-fmt="stories" onclick="selectFmt(this)"><div class="fmt-vis" style="width:18px;height:32px"></div><div class="fmt-label">Stories/<br>Reels</div></div>
        <div class="fmt-card" data-fmt="pinterest" onclick="selectFmt(this)"><div class="fmt-vis" style="width:22px;height:33px"></div><div class="fmt-label">Pinterest</div></div>
        <div class="fmt-card" data-fmt="tiktok" onclick="selectFmt(this)"><div class="fmt-vis" style="width:18px;height:32px"></div><div class="fmt-label">TikTok</div></div>
      </div>
      <div class="section-label">Content type</div>
      <div class="ct-grid">
        <div class="ct-pill active" data-ct="Quote / Inspirational" onclick="selectCT(this)">Quote</div>
        <div class="ct-pill" data-ct="Product showcase" onclick="selectCT(this)">Product</div>
        <div class="ct-pill" data-ct="Educational tip" onclick="selectCT(this)">Tip</div>
        <div class="ct-pill" data-ct="Announcement / Launch" onclick="selectCT(this)">Announce</div>
        <div class="ct-pill" data-ct="Testimonial / Review" onclick="selectCT(this)">Testimonial</div>
        <div class="ct-pill" data-ct="Promotion / Offer" onclick="selectCT(this)">Promo</div>
        <div class="ct-pill" data-ct="Before & after" onclick="selectCT(this)">Before/After</div>
        <div class="ct-pill" data-ct="Behind the scenes" onclick="selectCT(this)">BTS</div>
      </div>
    </div>
    <div class="card card-pad" style="margin-bottom:16px">
      <div class="section-label">Copy</div>
      <div class="field"><label>Headline <span style="color:var(--muted);font-weight:400">(required)</span></label><input type="text" id="inHeadline" placeholder="Your main message..." oninput="debouncedPreview()"></div>
      <div class="field"><label>Subtext <span style="color:var(--muted);font-weight:400">(optional)</span></label><input type="text" id="inSubtext" placeholder="Supporting line..." oninput="debouncedPreview()"></div>
      <div class="field"><label>CTA button text</label><input type="text" id="inCta" placeholder="e.g. Learn more" oninput="debouncedPreview()"></div>
    </div>
    <button class="btn btn-primary" id="generateBtn" onclick="generate()" disabled>Generate image</button>
  </div>
  <div class="preview-panel">
    <div class="card">
      <div class="preview-box" id="previewBox">
        <div class="loading-overlay" id="loadingOverlay"><div class="spinner"></div><span>Generating...</span></div>
        <div class="preview-placeholder" id="previewPlaceholder"><div class="preview-placeholder-icon">🎨</div><p>Select a brand and fill in your copy to preview</p></div>
        <img class="preview-img" id="previewImg" alt="Preview">
      </div>
      <div class="preview-actions">
        <button class="btn btn-secondary" id="downloadBtn" onclick="downloadImage()" disabled>⬇ Download PNG</button>
        <button class="btn btn-secondary" id="allFormatsBtn" onclick="downloadAll()" disabled>All 5 formats</button>
      </div>
    </div>
    <div class="hint-box" id="hintBox" style="display:none">
      <div class="hint-card"><div class="section-label" style="margin-bottom:8px">Copy hints</div><div id="hintContent"></div></div>
    </div>
  </div>
</div>

<div class="modal-overlay" id="modalOverlay" onclick="closeModalIfBg(event)">
  <div class="modal">
    <div class="modal-header"><div class="modal-title">Add a brand</div><button class="modal-close" onclick="closeModal()">✕</button></div>
    <div class="modal-body">
      <div class="field"><label>Brand name *</label><input type="text" id="m_name" placeholder="e.g. City Food Bank"></div>
      <div class="field-row">
        <div class="field"><label>Industry / cause</label><input type="text" id="m_industry" placeholder="e.g. Food security"></div>
        <div class="field"><label>CTA text</label><input type="text" id="m_cta" placeholder="Donate now" value="Learn more"></div>
      </div>
      <div class="field"><label>Target audience</label><input type="text" id="m_audience" placeholder="e.g. Local donors and volunteers"></div>
      <div class="field-row">
        <div class="field"><label>Tagline</label><input type="text" id="m_tagline" placeholder="Optional"></div>
        <div class="field"><label>Handle / website</label><input type="text" id="m_handle" placeholder="@org or org.org"></div>
      </div>
      <div class="fsec">Tone</div>
      <div class="tone-grid">
        <div class="tone-opt" onclick="selectTone(this)">Luxury / Elevated</div>
        <div class="tone-opt" onclick="selectTone(this)">Playful / Fun</div>
        <div class="tone-opt selected" onclick="selectTone(this)">Minimal / Clean</div>
        <div class="tone-opt" onclick="selectTone(this)">Bold / Edgy</div>
        <div class="tone-opt" onclick="selectTone(this)">Warm / Approachable</div>
        <div class="tone-opt" onclick="selectTone(this)">Earthy / Organic</div>
        <div class="tone-opt" onclick="selectTone(this)">Professional</div>
        <div class="tone-opt" onclick="selectTone(this)">Vibrant / Energetic</div>
      </div>
      <div class="fsec">Colors</div>
      <div class="field-row">
        <div class="field"><label>Primary *</label><div class="color-field"><input type="color" id="m_cp_p" value="#1A1916" oninput="syncHex('m_cp_p','m_ct_p')"><input type="text" id="m_ct_p" value="#1A1916" oninput="syncColor('m_ct_p','m_cp_p')"></div></div>
        <div class="field"><label>Secondary</label><div class="color-field"><input type="color" id="m_cp_s" value="#F0EDE8" oninput="syncHex('m_cp_s','m_ct_s')"><input type="text" id="m_ct_s" value="#F0EDE8" oninput="syncColor('m_ct_s','m_cp_s')"></div></div>
      </div>
      <div class="field-row">
        <div class="field"><label>Accent</label><div class="color-field"><input type="color" id="m_cp_a" value="#555555" oninput="syncHex('m_cp_a','m_ct_a')"><input type="text" id="m_ct_a" value="#555555" oninput="syncColor('m_ct_a','m_cp_a')"></div></div>
        <div class="field"><label>Background</label><div class="color-field"><input type="color" id="m_cp_b" value="#FFFFFF" oninput="syncHex('m_cp_b','m_ct_b')"><input type="text" id="m_ct_b" value="#FFFFFF" oninput="syncColor('m_ct_b','m_cp_b')"></div></div>
      </div>
      <div class="field" style="max-width:260px"><label>Text color</label><div class="color-field"><input type="color" id="m_cp_t" value="#222222" oninput="syncHex('m_cp_t','m_ct_t')"><input type="text" id="m_ct_t" value="#222222" oninput="syncColor('m_ct_t','m_cp_t')"></div></div>
      <div class="fsec">Fonts <span style="font-weight:400;color:var(--muted);text-transform:none;letter-spacing:0">— use Google Font names</span></div>
      <div class="field-row">
        <div class="field"><label>Heading font</label><input type="text" id="m_fh" placeholder="Playfair Display, Montserrat..."><small style="font-size:.72rem;color:var(--muted);margin-top:3px;display:block">Available: Playfair Display, Montserrat, Lato, Open Sans, Inter</small></div>
        <div class="field"><label>Body font</label><input type="text" id="m_fb" placeholder="Lato, Open Sans, Inter..."></div>
      </div>
      <div class="fsec">Logo (optional)</div>
      <div class="field"><input type="file" id="m_logo" accept="image/*"><small style="font-size:.72rem;color:var(--muted);margin-top:3px;display:block">PNG with transparent background works best</small></div>
      <div id="m_error" style="color:#c0392b;font-size:.8rem;margin-top:8px"></div>
    </div>
    <div class="modal-footer">
      <button class="btn btn-secondary btn-sm" onclick="closeModal()">Cancel</button>
      <button class="btn btn-primary btn-sm" style="width:auto" onclick="submitBrand()">Save brand</button>
    </div>
  </div>
</div>
<div class="toast" id="toast"></div>

<script>
const COPY_HINTS = {
  'Quote / Inspirational': {hl:'[Quote in 8 words or fewer]',sub:'— Brand name or attribution',cta:'Learn more / Save this'},
  'Product showcase':      {hl:'[Product name] — [one-word benefit]',sub:'[What it does] for [who]',cta:'Shop now / View product'},
  'Educational tip':       {hl:'[Tip in 6 words]',sub:'[Supporting detail or first step]',cta:'Read more / Save this'},
  'Announcement / Launch': {hl:'Introducing [Product / News]',sub:'[Available now / Date]',cta:'Learn more / Register'},
  'Before & after':        {hl:'Before. → After.',sub:'[What changed + timeframe]',cta:'See how / Book now'},
  'Testimonial / Review':  {hl:'"[Customer quote, ≤8 words]"',sub:'— [First name, context]',cta:'Read more / Join us'},
  'Promotion / Offer':     {hl:'[X% off] [Product]',sub:'Ends [date] · Code [CODE]',cta:'Shop now / Claim offer'},
  'Behind the scenes':     {hl:"[What we're working on]",sub:'[Brief human detail]',cta:'Follow along'},
};

let brands=[], activeBrandId=null, activeFmt='ig_square', activeCT='Quote / Inspirational', debounceTimer=null;

async function init() {
  const res = await fetch('/api/brands');
  brands = await res.json();
  renderBrands();
  if (brands.length) selectBrand(brands[0].id);
  updateHints();
}

function renderBrands() {
  const list = document.getElementById('brandList');
  list.innerHTML = brands.map(b => `
    <div class="brand-item ${b.id===activeBrandId?'active':''}" onclick="selectBrand('${b.id}')">
      <div class="brand-dot" style="background:${b.colors?.primary||'#ccc'}"></div>
      <div class="brand-name">${esc(b.name)}</div>
      <div class="brand-del" onclick="event.stopPropagation();deleteBrand('${b.id}')" title="Remove">✕</div>
    </div>`).join('') || '<div style="font-size:.82rem;color:var(--muted)">No brands yet — add one.</div>';
}

function selectBrand(id) {
  activeBrandId = id;
  renderBrands();
  updateGenerateBtn();
  const b = brands.find(x=>x.id===id);
  if (b?.cta) document.getElementById('inCta').value = b.cta;
}

function selectFmt(el) {
  document.querySelectorAll('.fmt-card').forEach(c=>c.classList.remove('active'));
  el.classList.add('active');
  activeFmt = el.dataset.fmt;
  if (document.getElementById('previewImg').style.display!=='none') debouncedPreview();
}

function selectCT(el) {
  document.querySelectorAll('.ct-pill').forEach(c=>c.classList.remove('active'));
  el.classList.add('active');
  activeCT = el.dataset.ct;
  updateHints();
  if (document.getElementById('inHeadline').value) debouncedPreview();
}

function updateGenerateBtn() {
  document.getElementById('generateBtn').disabled = !activeBrandId;
}

function updateHints() {
  const h = COPY_HINTS[activeCT];
  if (!h) { document.getElementById('hintBox').style.display='none'; return; }
  document.getElementById('hintBox').style.display='block';
  document.getElementById('hintContent').innerHTML =
    `<div style="margin-bottom:5px"><strong>Headline:</strong> ${esc(h.hl)}</div>
     <div style="margin-bottom:5px"><strong>Subtext:</strong> ${esc(h.sub)}</div>
     <div><strong>CTA:</strong> ${esc(h.cta)}</div>`;
}

function debouncedPreview() {
  updateGenerateBtn();
  clearTimeout(debounceTimer);
  debounceTimer = setTimeout(()=>{
    if (activeBrandId && document.getElementById('inHeadline').value.trim()) generate(true);
  }, 700);
}

async function generate(preview=false) {
  if (!activeBrandId) return;
  const brand = brands.find(b=>b.id===activeBrandId);
  const headline = document.getElementById('inHeadline').value.trim() || brand?.name || '';
  document.getElementById('loadingOverlay').style.display='flex';
  document.getElementById('previewPlaceholder').style.display='none';
  try {
    const res = await fetch('/api/generate', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({brandId:activeBrandId,format:activeFmt,headline,
        subtext:document.getElementById('inSubtext').value.trim(),
        cta:document.getElementById('inCta').value.trim(), contentType:activeCT})
    });
    const data = await res.json();
    if (data.image) {
      const img = document.getElementById('previewImg');
      img.src = 'data:image/png;base64,'+data.image;
      img.style.display='block';
      document.getElementById('downloadBtn').disabled=false;
      document.getElementById('allFormatsBtn').disabled=false;
    }
  } catch(e) { showToast('Generation failed'); }
  document.getElementById('loadingOverlay').style.display='none';
}

async function downloadImage() {
  const brand = brands.find(b=>b.id===activeBrandId);
  const res = await fetch('/api/download', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({brandId:activeBrandId,format:activeFmt,
      headline:document.getElementById('inHeadline').value.trim()||brand?.name||'',
      subtext:document.getElementById('inSubtext').value.trim(),
      cta:document.getElementById('inCta').value.trim(), contentType:activeCT})
  });
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a'); a.href=url;
  a.download=(brand?.name||'image').toLowerCase().replace(/\s+/g,'_')+'_'+activeFmt+'.png';
  a.click(); URL.revokeObjectURL(url);
}

async function downloadAll() {
  const fmts = ['ig_square','ig_portrait','stories','pinterest','tiktok'];
  const brand = brands.find(b=>b.id===activeBrandId);
  showToast('Generating all formats...');
  for (const fmt of fmts) {
    const res = await fetch('/api/download', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({brandId:activeBrandId,format:fmt,
        headline:document.getElementById('inHeadline').value.trim()||brand?.name||'',
        subtext:document.getElementById('inSubtext').value.trim(),
        cta:document.getElementById('inCta').value.trim(), contentType:activeCT})
    });
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a'); a.href=url;
    a.download=(brand?.name||'image').toLowerCase().replace(/\s+/g,'_')+'_'+fmt+'.png';
    a.click(); URL.revokeObjectURL(url);
    await new Promise(r=>setTimeout(r,300));
  }
  showToast('All 5 formats downloaded!');
}

async function deleteBrand(id) {
  if (!confirm('Remove this brand?')) return;
  await fetch('/api/brands/'+id, {method:'DELETE'});
  brands = brands.filter(b=>b.id!==id);
  if (activeBrandId===id) activeBrandId = brands[0]?.id||null;
  renderBrands(); updateGenerateBtn();
}

function openModal() { document.getElementById('modalOverlay').classList.add('open'); }
function closeModal() { document.getElementById('modalOverlay').classList.remove('open'); }
function closeModalIfBg(e) { if(e.target===document.getElementById('modalOverlay')) closeModal(); }
function selectTone(el) { document.querySelectorAll('.tone-opt').forEach(o=>o.classList.remove('selected')); el.classList.add('selected'); }
function syncHex(cid,tid) { document.getElementById(tid).value=document.getElementById(cid).value; }
function syncColor(tid,cid) { const v=document.getElementById(tid).value.trim(); if(/^#[0-9a-fA-F]{6}$/.test(v)) document.getElementById(cid).value=v; }

async function submitBrand() {
  const name = document.getElementById('m_name').value.trim();
  if (!name) { document.getElementById('m_error').textContent='Brand name is required.'; return; }
  const tone = document.querySelector('.tone-opt.selected')?.textContent||'Minimal / Clean';
  const brand = {name, tagline:document.getElementById('m_tagline').value.trim(),
    industry:document.getElementById('m_industry').value.trim(),
    audience:document.getElementById('m_audience').value.trim(), tone,
    colors:{primary:document.getElementById('m_ct_p').value.trim(),
      secondary:document.getElementById('m_ct_s').value.trim(),
      accent:document.getElementById('m_ct_a').value.trim(),
      background:document.getElementById('m_ct_b').value.trim(),
      text:document.getElementById('m_ct_t').value.trim()},
    fonts:{heading:document.getElementById('m_fh').value.trim()||'Inter',
      body:document.getElementById('m_fb').value.trim()||'Inter'},
    cta:document.getElementById('m_cta').value.trim()||'Learn more',
    handle:document.getElementById('m_handle').value.trim()};
  const res = await fetch('/api/brands',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(brand)});
  const saved = await res.json();
  brands.push(saved);
  const logoFile = document.getElementById('m_logo').files[0];
  if (logoFile) {
    const fd = new FormData(); fd.append('logo',logoFile);
    await fetch('/api/upload-logo/'+saved.id,{method:'POST',body:fd});
  }
  renderBrands(); selectBrand(saved.id); closeModal(); showToast('Brand saved!');
  document.getElementById('m_name').value=''; document.getElementById('m_error').textContent='';
}

function esc(s){return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}
function showToast(msg){const t=document.getElementById('toast');t.textContent=msg;t.classList.add('show');setTimeout(()=>t.classList.remove('show'),2500);}

init();
</script>
</body>
</html>"""

if __name__ == "__main__":
    print("\n  Brand Image Generator")
    print(f"  Supabase: {'connected' if USE_SUPABASE else 'not configured (using local storage)'}")
    print("  Open: http://localhost:5000\n")
    app.run(debug=False, port=5000)
