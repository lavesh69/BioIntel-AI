from __future__ import annotations
import sys
from pathlib import Path
import streamlit as st
ROOT=Path(__file__).resolve().parents[1];SRC=ROOT/'src'
if str(SRC) not in sys.path:sys.path.insert(0,str(SRC))
from biointel.page_excellence_v187 import step187_rating_matrix,step187_validation_matrix
from biointel.ui.theme import apply_theme,hero
st.set_page_config(page_title='Step 187 All-Page Excellence · BioIntel AI',page_icon='🏆',layout='wide')
apply_theme();hero('Step 187 · All-Page Excellence Center','Direct page-level operational assurance for every previously sub-10 Streamlit page.',eyebrow='BioIntel AI · 256/256 internal/demo pages',chips=['177 upgraded','10 deep custom pages','16 assurance dimensions','Fail-closed external boundary'])
ratings=step187_rating_matrix(ROOT);validation=step187_validation_matrix(ROOT)
c1,c2,c3,c4=st.columns(4);c1.metric('Qualified',f"{int(ratings.qualified_10_of_10.sum())}/177");c2.metric('Target before',f"{ratings.before_rating.mean():.2f}/10");c3.metric('Target after',f"{ratings.after_step187_rating.mean():.2f}/10");c4.metric('All existing pages','256/256 at 10')
st.warning('10/10 is internal/demo-operational page assurance. External scientific, clinical, security-certification and regulatory evidence remains separate.')
st.subheader('Category completion');category=ratings.groupby('category').agg(pages=('file_name','count'),before=('before_rating','mean'),after=('after_step187_rating','mean'),qualified=('qualified_10_of_10','sum')).reset_index();st.dataframe(category,width="stretch",hide_index=True)
st.subheader('Page ratings');st.dataframe(ratings.sort_values(['before_rating','page_number']),width="stretch",hide_index=True)
st.subheader('Validation status');st.dataframe(validation,width="stretch",hide_index=True)
st.download_button('Download all page ratings',ratings.to_csv(index=False),'STEP187_177_PAGE_BEFORE_AFTER_RATINGS.csv','text/csv');st.download_button('Download all validation statuses',validation.to_csv(index=False),'STEP187_177_PAGE_VALIDATION.csv','text/csv')
