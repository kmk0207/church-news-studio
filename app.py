"""로컬 실행: python -m streamlit run app.py"""

from pathlib import Path

from church_studio.ui import main

main(Path(__file__).resolve().parent)
