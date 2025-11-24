#=========== report.py ==========

def generate_html(data,filename):
   
    data = sorted(
    (
        job for job in data
        if isinstance(job, dict) 
        and isinstance(job.get("score"), (float, int)) 
        and job.get("score") is not None
        and job.get("score") > 0.5  # threshold
    ),
    key=lambda x: x["score"],
    reverse=True
                )


    scraped_jobs = len(data)
    skill_match_count = sum(1 for job in data if job.get("skillMatch"))
    not_ext_app_count = sum(1 for job in data if not job.get("extApp"))
    both_count = sum(1 for job in data if job.get("skillMatch") and not job.get("extApp"))
    
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Filtered Job Listings</title>
    <style>
        * {{
    box-sizing: border-box;
}}

body {{
    font-family: "Segoe UI", Roboto, sans-serif;
    margin: 0;
    padding: 0;
    background-color: #f5f7fa;
    color: #222;
    height: 100vh;
    overflow: hidden;
}}

.header-container {{
    display: flex;
    align-items: center;
    background-color: #ffffff;
    padding: 16px 24px;
    border-bottom: 1px solid #e0e0e0;
    box-shadow: 0 2px 4px rgba(0,0,0,0.04);
}}

.logo {{
    height: 40px;
    margin-right: 16px;
}}

.header-title {{
    position: absolute;
    left: 50%;
    transform: translateX(-50%);
    font-size: 24px;
    font-weight: 600;
    color: #b00020;
}}

/* Main container split into sidebar (left) + job section (right) */
.container {{
    display: flex;
    height: calc(100vh - 72px);
}}

/* Sidebar that stacks controls and summary vertically */
.sidebar {{
    display: flex;
    flex-direction: column;
    width: 300px;
    margin: 16px;
}}

/* Controls + Summary Table Common Styles */
.controls, .summary-table {{
    background-color: #ffffff;
    margin-bottom: 16px;
    padding: 10px;
    border-radius: 10px;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.06);
    overflow-y: auto;
}}

/* Controls specific styles */
.controls label {{
    display: block;
    font-size: 14px;
    margin-top: 12px;
}}

.controls input[type="number"] {{
    width: 100%;
    padding: 8px;
    border-radius: 6px;
    border: 1px solid #ccc;
}}

.controls button {{
    margin-top: 20px;
    width: 100%;
    padding: 10px;
    background-color: #b00020;
    color: white;
    border: none;
    border-radius: 6px;
    font-weight: 500;
    cursor: pointer;
    transition: background 0.2s;
}}

.controls button:hover {{
    background-color: #8e001a;
}}

.toggle-container {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin: 10px 0;
}}

.toggle-container span {{
    font-size: 14px;
}}

.switch {{
    position: relative;
    display: inline-block;
    width: 40px;
    height: 22px;
}}

.switch input {{
    opacity: 0;
    width: 0;
    height: 0;
}}

.slider {{
    position: absolute;
    cursor: pointer;
    top: 0; left: 0;
    right: 0; bottom: 0;
    background-color: #ccc;
    transition: .4s;
    border-radius: 34px;
}}

.slider:before {{
    position: absolute;
    content: "";
    height: 16px;
    width: 16px;
    left: 3px;
    bottom: 3px;
    background-color: white;
    transition: .4s;
    border-radius: 50%;
}}

input:checked + .slider {{
    background-color: #b00020;
}}

input:checked + .slider:before {{
    transform: translateX(18px);
}}

/* Summary Table styles */
.summary-table h4 {{
    font-size: 16px;
    font-weight: 600;
    margin: 0 0 12px 0;
}}

.summary-table table {{
    width: 100%;
    border-collapse: collapse;
}}

.summary-table th, .summary-table td {{
    padding: 8px;
    font-size: 14px;
    border: 1px solid #ccc; /* full borders for each cell */
}}

.summary-table th {{
    color: #b00020;
    text-align: left;
}}

/* Job section styles */
.job-section {{
    flex: 1;
    margin: 16px 16px 16px 0;
    overflow-y: auto;
}}

.job-table {{
    width: 100%;
    border-collapse: collapse; /* ensures borders are shared */
    background-color: #fff;
    border-radius: 10px;
    overflow: hidden;
    box-shadow: 0 4px 12px rgba(0,0,0,0.05);
}}

.job-table thead {{
    background-color: #f9f9f9;
}}

.job-table th, .job-table td {{
    padding: 12px;
    font-size: 14px;
    border: 1px solid #ccc; /* individual borders for each cell */
}}

.job-table th {{
    color: #333;
    font-weight: 600;
    cursor: pointer;
}}

.job-table tr:hover {{
    background-color: #f1f1f1;
}}

.job-table th.sort-asc::after {{
    content: " 🔼";
    font-size: 12px;
}}

.job-table th.sort-desc::after {{
    content: " 🔽";
    font-size: 12px;
}}

/* Score coloring */
.score-high {{ background-color: #b3ffb3; }}
.score-mid  {{ background-color: #ffffb3; }}
.score-low  {{ background-color: #ffcccc; }}

/* Hover always wins */
.job-table tr:hover {{
    background-color: #f1f1f1 !important;
}}
tr.auto-applied {{
    border: 2px solid #006400 !important; /* dark green */
}}
.filter-group {{
    background-color: #ffffff;
    padding: 14px 16px;
    margin-bottom: 16px;
    border-radius: 12px;
    box-shadow: 0 6px 18px rgba(0,0,0,0.08);
    font-size: 14px;
    transition: transform 0.2s, box-shadow 0.2s;
}}

.filter-group:hover {{
    transform: translateY(-2px);
    box-shadow: 0 8px 24px rgba(0,0,0,0.12);
}}

.filter-name {{
    font-weight: 600;
    margin-bottom: 8px;
    display: block;
    color: #b00020;
    font-size: 15px;
}}

/* True/False checkboxes aligned in row */
.filter-group label {{
    display: inline-flex;
    align-items: center;
    margin-right: 16px;
    font-weight: 500;
    cursor: pointer;
    padding: 4px 8px;
    border-radius: 6px;
    transition: background-color 0.2s, color 0.2s;
}}

.filter-group label:hover {{
    background-color: #f2f2f2;
}}

.filter-group input[type="checkbox"] {{
    margin-right: 6px;
    width: 18px;
    height: 18px;
    accent-color: #b00020;
    cursor: pointer;
    transition: transform 0.1s;
}}

.filter-group input[type="checkbox"]:hover {{
    transform: scale(1.1);
}}


    </style>
</head>
<body>
    <div class="header-container">
        <img src="https://i.ibb.co/9mPXLmSN/logo-removebg-preview.png" class="logo" alt="Logo">
        <h1 class="header-title">Naukri Job Crawler Summary</h1>
    </div>
    <div class="container">
    <div class="sidebar">
        <div class="controls">
    <label for="startIdx">Start Index:</label>
    <input type="number" id="startIdx" value="0">
    <label for="endIdx">End Index:</label>
    <input type="number" id="endIdx" value="50">
    <button onclick="openJobLinks()">Open Links</button>

    <!-- Boolean Filters -->
    <div class="filter-group">
        <span class="filter-name">External App</span>
        <label><input type="checkbox" id="extAppTrue" onchange="applyFilters()"> True</label>
        <label><input type="checkbox" id="extAppFalse" onchange="applyFilters()"> False</label>
    </div>

    <div class="filter-group">
        <span class="filter-name">Skill Match</span>
        <label><input type="checkbox" id="skillMatchTrue" onchange="applyFilters()"> True</label>
        <label><input type="checkbox" id="skillMatchFalse" onchange="applyFilters()"> False</label>
    </div>

    <div class="filter-group">
        <span class="filter-name">Auto Apply</span>
        <label><input type="checkbox" id="autoApplyTrue" onchange="applyFilters()"> True</label>
        <label><input type="checkbox" id="autoApplyFalse" onchange="applyFilters()"> False</label>
    </div>

    <div class="filter-group">
        <span class="filter-name">Early Applicant</span>
        <label><input type="checkbox" id="earlyAppTrue" onchange="applyFilters()"> True</label>
        <label><input type="checkbox" id="earlyAppFalse" onchange="applyFilters()"> False</label>
    </div>

    <div class="filter-group">
        <span class="filter-name">Location Match</span>
        <label><input type="checkbox" id="locationMatchTrue" onchange="applyFilters()"> True</label>
        <label><input type="checkbox" id="locationMatchFalse" onchange="applyFilters()"> False</label>
    </div>

    <div class="filter-group">
        <span class="filter-name">Experience Match</span>
        <label><input type="checkbox" id="experienceMatchTrue" onchange="applyFilters()"> True</label>
        <label><input type="checkbox" id="experienceMatchFalse" onchange="applyFilters()"> False</label>
    </div>
</div>


        <div class="summary-table">
            <h4>Summary</h4>
            <table>
                <tbody>
                    <tr><th>Total Jobs</th><td>{scraped_jobs}</td></tr>
                    <tr><th>Skill Match</th><td>{skill_match_count}</td></tr>
                    <tr><th>Not External App</th><td>{not_ext_app_count}</td></tr>
                    <tr><th>Skill Match & Not External</th><td>{both_count}</td></tr>
                </tbody>
            </table>
            <p><strong>Visible Jobs:</strong> <span id="visibleCount">0</span></p>
        </div>
        </div>
        <div class="job-section">
            <table class="job-table" id="jobTable">
                <thead>
                    <tr>
                        <th>#</th>
                        <th>Job Title</th>
                        <th>Company</th>
                        <th onclick="sortByPosted(this)">Posted</th>
                        <th>location</th>
                        <th>Applications</th>
                        
                        <th>URL</th>
                        <th>External</th>
                        <th>Skill Match</th>
                        <th onclick="sortByScore(this)">Score</th>
                        <th>Auto Apply Status</th>
                    </tr>
                </thead>
                <tbody>"""

    for idx, job in enumerate(data, 1):
        
        score = job.get("score", 0) * 100


        if score > 75:
            row_class = "score-high"
        elif score > 60:
            row_class = "score-mid"
        else:
            row_class = "score-low"

        if job.get("auto_apply_status") is True:
            row_class += " auto-applied"
            
        html_content += f"""
<tr class="{row_class}" data-extapp="{str(job.get('extApp', False)).lower()}" data-skillmatch="{str(job.get('skillMatch', False)).lower()}" data-earlyapp="{str(job.get('earlyApplicant', False)).lower()}" data-locationmatch="{str(job.get('locationMatch', False)).lower()}" data-experiencematch="{str(job.get('experienceMatch', False)).lower()}">
            <td>{idx}</td>
            <td>{job.get("Job Title", "")}</td>
            <td>{job.get("Company Name", "")}</td>
            <td>{job.get("age", "")}</td>
            <td>{job.get("location", "")}</td>
            <td>{job.get("applicants_text", "")}</td>
            
            <td><a href="{job.get("URL", "#")}" target="_blank">Link</a></td>
            <td>{job.get("extApp", "")}</td>
            <td>{job.get("skillMatch", "")}</td>
            <td>{score:.2f}%</td>
            <td title="{job.get('reason', '')}">{job.get("auto_apply_status", None)}</td>

        </tr>"""

    html_content += """
                </tbody>
            </table>
        </div>
    </div>

    <script>
        function applyFilters() {
    const filters = {
        extApp: [document.getElementById("extAppTrue").checked, document.getElementById("extAppFalse").checked],
        skillMatch: [document.getElementById("skillMatchTrue").checked, document.getElementById("skillMatchFalse").checked],
        autoApply: [document.getElementById("autoApplyTrue").checked, document.getElementById("autoApplyFalse").checked],
        earlyApp: [document.getElementById("earlyAppTrue").checked, document.getElementById("earlyAppFalse").checked],
        locationMatch: [document.getElementById("locationMatchTrue").checked, document.getElementById("locationMatchFalse").checked],
        experienceMatch: [document.getElementById("experienceMatchTrue").checked, document.getElementById("experienceMatchFalse").checked]
    };

    let visibleCount = 0;

    document.querySelectorAll("#jobTable tbody tr").forEach(row => {
        const values = {
            extApp: row.getAttribute("data-extapp") === "true",
            skillMatch: row.getAttribute("data-skillmatch") === "true",
            autoApply: row.cells[10].innerText === "True",
            earlyApp: row.getAttribute("data-earlyapp") === "true",
            locationMatch: row.getAttribute("data-locationmatch") === "true",
            experienceMatch: row.getAttribute("data-experiencematch") === "true"
        };

        const show = Object.keys(filters).every(key => {
            const [trueChecked, falseChecked] = filters[key];
            return (trueChecked && values[key]) || (falseChecked && !values[key]) || (!trueChecked && !falseChecked);
        });

        row.style.display = show ? "" : "none";
        if (show) visibleCount++;
    });

    document.getElementById("visibleCount").innerText = visibleCount;
}


        document.addEventListener("DOMContentLoaded", () => applyFilters());
      

        function openJobLinks() {
            let startIdx = parseInt(document.getElementById("startIdx").value);
            let endIdx = parseInt(document.getElementById("endIdx").value);
            let visibleRows = Array.from(document.querySelectorAll("#jobTable tbody tr"))
                                    .filter(row => row.style.display !== "none");

            visibleRows.forEach((row, index) => {
                if (index >= startIdx && index < endIdx) {
                    let link = row.querySelector("td:nth-child(7) a");
                    if (link && link.href) window.open(link.href, '_blank');
                }
            });
        }

        function extractPostedValue(text) {
            const match = text.match(/\\d+/);
            return match ? parseInt(match[0]) : 1;
        }

        function sortByPosted(header) {
            const tbody = document.querySelector("#jobTable tbody");
            const rows = Array.from(tbody.rows);
            const asc = !header.classList.contains("sort-asc");
            rows.sort((a, b) => {
                const aVal = extractPostedValue(a.cells[3].innerText);
                const bVal = extractPostedValue(b.cells[3].innerText);
                return asc ? aVal - bVal : bVal - aVal;
            });
            rows.forEach(row => tbody.appendChild(row));
            document.querySelectorAll("th").forEach(th => th.classList.remove("sort-asc", "sort-desc"));
            header.classList.add(asc ? "sort-asc" : "sort-desc");
        }

        function sortByScore(header) {
            const tbody = document.querySelector("#jobTable tbody");
            const rows = Array.from(tbody.rows);
            const asc = !header.classList.contains("sort-asc");
            rows.sort((a, b) => {
                const aVal = parseFloat(a.cells[9].innerText);
                const bVal = parseFloat(b.cells[9].innerText);
                return asc ? aVal - bVal : bVal - aVal;
            });
            rows.forEach(row => tbody.appendChild(row));
            document.querySelectorAll("th").forEach(th => th.classList.remove("sort-asc", "sort-desc"));
            header.classList.add(asc ? "sort-asc" : "sort-desc");
        }
    </script>
</body>
</html>"""

    with open(filename, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"HTML Report saved at {filename}")


# import json
# import os
# from datetime import datetime

# # # ==== Load Data ====
# json_path = r"C:\Users\imjad\Desktop\case study\st\oneClickShell\outputs\run_20250828_131949\job_data_20250828_131949.json"

# with open(json_path, "r", encoding="utf-8") as f:
#     data = json.load(f)

# # ==== Create Filename ====
# timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

# # Get same folder as JSON and create filename
# output_dir = os.path.dirname(json_path)
# output_path = os.path.join(output_dir, f"summary_crawler_{timestamp}.html")

# # ==== Generate HTML ====
# generate_html(data, output_path)

