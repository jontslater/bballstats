# How to Run Scripts - Quick Guide

## ⚠️ Important: Scripts are in the ROOT directory, not backend!

All scripts are in `/Users/lisaannparr/bballstats/scripts/` (project root), not in the backend folder.

---

## ✅ Correct Way to Run Scripts

### Step 1: Navigate to Project Root
```bash
cd /Users/lisaannparr/bballstats
# NOT: cd backend
```

### Step 2: Activate Backend Virtual Environment
```bash
source backend/venv/bin/activate
```

### Step 3: Run the Script
```bash
python scripts/update_all.py
```

---

## 📝 Complete Example

```bash
# Start from anywhere, navigate to project root
cd /Users/lisaannparr/bballstats

# Activate the virtual environment
source backend/venv/bin/activate

# Now you can run any script
python scripts/update_all.py
python scripts/generate_predictions.py
python scripts/check_collection_progress.py
```

---

## 🎯 Common Scripts

### Update Everything (including predictions)
```bash
cd /Users/lisaannparr/bballstats
source backend/venv/bin/activate
python scripts/update_all.py
```

### Generate Predictions Only
```bash
cd /Users/lisaannparr/bballstats
source backend/venv/bin/activate
python scripts/generate_predictions.py
```

### Check Data Status
```bash
cd /Users/lisaannparr/bballstats
source backend/venv/bin/activate
python scripts/check_collection_progress.py
```

---

## ❌ Common Mistakes

### Wrong: Running from backend directory
```bash
cd backend
python scripts/update_all.py  # ❌ Scripts not here!
```

### Wrong: Not activating virtual environment
```bash
cd /Users/lisaannparr/bballstats
python scripts/update_all.py  # ❌ Missing dependencies!
```

### Wrong: Wrong path to script
```bash
cd /Users/lisaannparr/bballstats
source backend/venv/bin/activate
python update_all.py  # ❌ Script is in scripts/ folder!
```

---

## ✅ Correct Path Structure

```
/Users/lisaannparr/bballstats/          ← Run scripts from HERE
├── backend/
│   ├── venv/                            ← Activate this
│   └── app/
├── frontend/
├── scripts/                             ← Scripts are HERE
│   ├── update_all.py
│   ├── generate_predictions.py
│   └── ...
└── ...
```

---

## 🚀 Quick Reference

**Always:**
1. `cd /Users/lisaannparr/bballstats` (project root)
2. `source backend/venv/bin/activate` (activate venv)
3. `python scripts/[script_name].py` (run script)

**Or use the frontend button** - No scripts needed! 🎉


