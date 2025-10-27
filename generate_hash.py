import streamlit_authenticator as stauth

password = 'timus891'

hasher = stauth.Hasher()
hashed_password = hasher.hash(password)

print(hashed_password)

