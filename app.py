import streamlit as st

st.set_page_config(page_title="Step 1 Web Portal", page_icon="🧪", layout="centered")
st.title("Step 1 Demo – Interactive Fields (no storage)")
st.caption("Enter data, compute results instantly. Nothing is stored on the server.")

with st.form("calc_form", clear_on_submit=False):
    st.subheader("Input data")
    name = st.text_input("Your name", placeholder="...")
    col1, col2 = st.columns(2)
    with col1:
        a = st.number_input("Value A", value=10.0, step=0.1)
    with col2:
        b = st.number_input("Value B", value=5.0, step=0.1)

    operation = st.selectbox(
        "Operation",
        [
            "Add (A + B)",
            "Subtract (A - B)",
            "Multiply (A × B)",
            "Divide (A ÷ B)",
            "Mean of A & B",
            "Euclidean norm √(A² + B²)",
        ],
        index=0,
    )
    apply_vat = st.checkbox("Add VAT 7.7% to result (example)")

    submitted = st.form_submit_button("Compute", type="primary")

if submitted:
    if operation == "Add (A + B)":
        result = a + b
        formula = "A + B"
    elif operation == "Subtract (A - B)":
        result = a - b
        formula = "A - B"
    elif operation == "Multiply (A × B)":
        result = a * b
        formula = "A × B"
    elif operation == "Divide (A ÷ B)":
        if b == 0:
            st.error("Cannot divide by zero.")
            st.stop()
        result = a / b
        formula = "A ÷ B"
    elif operation == "Mean of A & B":
        result = (a + b) / 2
        formula = "(A + B) / 2"
    else:
        result = (a**2 + b**2) ** 0.5
        formula = "√(A² + B²)"

    if apply_vat:
        result *= 1.077

    st.success("Computed successfully.")
    if name:
        st.write(f"Hello, **{name}**!")
    st.metric(label="Result", value=f"{result:,.4f}")
    with st.expander("Details"):
        st.write(f"Formula: {formula}")
        st.json(
            {
                "inputs": {"A": a, "B": b, "operation": operation, "apply_vat": apply_vat},
                "outputs": {"result": result},
            }
        )

st.divider()
st.caption("This app does not store your inputs or outputs. Refreshing the page resets the session.")
