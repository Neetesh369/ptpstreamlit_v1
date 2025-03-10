import streamlit as st

# Title of the app
st.title("IndexedDB Test App")

# HTML and JavaScript to interact with IndexedDB
html_code = """
<!DOCTYPE html>
<html>
<head>
    <title>IndexedDB Test</title>
</head>
<body>
    <h2>IndexedDB Test</h2>
    <button onclick="openDB()">Open Database</button>
    <button onclick="addData()">Add Data</button>
    <button onclick="readData()">Read Data</button>
    <button onclick="deleteDB()">Delete Database</button>
    <p id="status"></p>
    <p id="output"></p>

    <script>
        let db;
        const dbName = "TestDB";
        const storeName = "TestStore";

        function openDB() {
            const request = indexedDB.open(dbName, 1);

            request.onupgradeneeded = function(event) {
                db = event.target.result;
                if (!db.objectStoreNames.contains(storeName)) {
                    db.createObjectStore(storeName, { keyPath: "id" });
                }
                document.getElementById("status").innerText = "Database opened and store created.";
            };

            request.onsuccess = function(event) {
                db = event.target.result;
                document.getElementById("status").innerText = "Database opened successfully.";
            };

            request.onerror = function(event) {
                document.getElementById("status").innerText = "Error opening database.";
            };
        }

        function addData() {
            if (!db) {
                document.getElementById("status").innerText = "Database not opened.";
                return;
            }

            const transaction = db.transaction([storeName], "readwrite");
            const store = transaction.objectStore(storeName);
            const data = { id: 1, name: "Test Data" };

            const request = store.add(data);

            request.onsuccess = function() {
                document.getElementById("status").innerText = "Data added successfully.";
            };

            request.onerror = function() {
                document.getElementById("status").innerText = "Error adding data.";
            };
        }

        function readData() {
            if (!db) {
                document.getElementById("status").innerText = "Database not opened.";
                return;
            }

            const transaction = db.transaction([storeName], "readonly");
            const store = transaction.objectStore(storeName);
            const request = store.get(1);

            request.onsuccess = function() {
                if (request.result) {
                    document.getElementById("output").innerText = JSON.stringify(request.result);
                } else {
                    document.getElementById("output").innerText = "No data found.";
                }
            };

            request.onerror = function() {
                document.getElementById("output").innerText = "Error reading data.";
            };
        }

        function deleteDB() {
            const request = indexedDB.deleteDatabase(dbName);

            request.onsuccess = function() {
                document.getElementById("status").innerText = "Database deleted successfully.";
                document.getElementById("output").innerText = "";
            };

            request.onerror = function() {
                document.getElementById("status").innerText = "Error deleting database.";
            };
        }
    </script>
</body>
</html>
"""

# Display the HTML in the Streamlit app
st.components.v1.html(html_code, height=600)
