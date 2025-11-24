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
            margin: 0;
            padding: 0;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: #2d3748;
            font-size: 13px;
            line-height: 1.4;
            height: 100vh;
            overflow: hidden;
        }}

        /* Header */
        .header {{
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(10px);
            border-bottom: 1px solid rgba(255, 255, 255, 0.2);
            padding: 8px 16px;
            display: flex;
            align-items: center;
            box-shadow: 0 2px 20px rgba(0, 0, 0, 0.1);
        }}

        .logo {{
            height: 32px;
            margin-right: 12px;
        }}

        .title {{
            font-size: 18px;
            font-weight: 700;
            color: #4a5568;
            flex: 1;
            text-align: center;
        }}

        /* Summary Bar at top */
        .summary-bar {{
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(10px);
            border-radius: 12px;
            border: 1px solid rgba(255, 255, 255, 0.3);
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
            margin: 12px;
            padding: 16px;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }}

        /* Main Layout */
        .main-container {{
            display: flex;
            height: calc(100vh - 120px);
            gap: 12px;
            padding: 0 12px 12px;
        }}

        /* Sidebar */
        .sidebar {{
            width: 280px;
            display: flex;
            flex-direction: column;
            gap: 12px;
        }}

        .card {{
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(10px);
            border-radius: 12px;
            border: 1px solid rgba(255, 255, 255, 0.3);
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
            overflow: hidden;
        }}

        .card-header {{
            background: linear-gradient(90deg, #667eea, #764ba2);
            color: white;
            padding: 10px 14px;
            font-weight: 600;
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}

        .card-body {{
            padding: 12px;
        }}

        /* Controls */
        .control-group {{
            display: flex;
            gap: 8px;
            margin-bottom: 10px;
        }}

        .control-group label {{
            font-size: 11px;
            font-weight: 600;
            color: #4a5568;
            min-width: 40px;
        }}

        .control-group input {{
            flex: 1;
            padding: 4px 8px;
            border: 1px solid #e2e8f0;
            border-radius: 6px;
            font-size: 12px;
            background: #f7fafc;
            width: 80px;
        }}

        .btn {{
            width: 100%;
            padding: 8px 16px;
            background: linear-gradient(90deg, #667eea, #764ba2);
            color: white;
            border: none;
            border-radius: 8px;
            font-weight: 600;
            font-size: 12px;
            cursor: pointer;
            transition: all 0.2s;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}

        .btn:hover {{
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
        }}

        /* Filters */
        .filter-item {{
            margin-bottom: 8px;
            padding: 8px;
            background: #f8fafc;
            border-radius: 8px;
            border-left: 3px solid #667eea;
        }}

        .filter-label {{
            font-size: 11px;
            font-weight: 600;
            color: #2d3748;
            margin-bottom: 4px;
            text-transform: uppercase;
            letter-spacing: 0.3px;
        }}

        .filter-options {{
            display: flex;
            gap: 12px;
        }}

        .filter-options label {{
            display: flex;
            align-items: center;
            font-size: 11px;
            font-weight: 500;
            cursor: pointer;
            color: #4a5568;
        }}

        .filter-options input[type="checkbox"] {{
            width: 14px;
            height: 14px;
            margin-right: 6px;
            accent-color: #667eea;
        }}

        /* Summary */
        .summary-grid {{
            display: flex;
            gap: 16px;
        }}

        .summary-item {{
            text-align: center;
            padding: 8px 12px;
            background: linear-gradient(135deg, #f8fafc 0%, #e2e8f0 100%);
            border-radius: 8px;
            border: 1px solid #e2e8f0;
            min-width: 80px;
        }}

        .summary-item .value {{
            font-size: 16px;
            font-weight: 700;
            color: #2d3748;
        }}

        .summary-item .label {{
            font-size: 10px;
            color: #718096;
            text-transform: uppercase;
            letter-spacing: 0.3px;
            margin-top: 2px;
            white-space: nowrap;
        }}

        .visible-count {{
            text-align: center;
            padding: 8px 16px;
            background: linear-gradient(90deg, #48bb78, #38a169);
            color: white;
            border-radius: 8px;
            font-weight: 600;
            font-size: 12px;
        }}

        /* Job Table */
        .job-container {{
            flex: 1;
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(10px);
            border-radius: 12px;
            border: 1px solid rgba(255, 255, 255, 0.3);
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
            overflow: hidden;
            display: flex;
            flex-direction: column;
        }}

        .table-header {{
            background: linear-gradient(90deg, #2d3748, #4a5568);
            color: white;
            padding: 10px 14px;
            font-weight: 600;
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}

        .table-container {{
            flex: 1;
            overflow: auto;
        }}

        .job-table {{
            width: 100%;
            border-collapse: collapse;
        }}

        .job-table th {{
            background: #f7fafc;
            color: #2d3748;
            padding: 8px 10px;
            font-size: 11px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.3px;
            border-bottom: 2px solid #e2e8f0;
            position: sticky;
            top: 0;
            cursor: pointer;
            transition: background 0.2s;
        }}

        .job-table th:hover {{
            background: #edf2f7;
        }}

        .job-table td {{
            padding: 6px 10px;
            font-size: 12px;
            border-bottom: 1px solid #f1f5f9;
            vertical-align: middle;
        }}

        .job-table tr {{
            transition: all 0.2s;
        }}

        .job-table tr:hover {{
            background: #f8fafc !important;
            transform: scale(1.002);
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
        }}

        /* Score styling */
        .score-high {{ background: linear-gradient(90deg, #c6f6d5, #9ae6b4); }}
        .score-mid {{ background: linear-gradient(90deg, #fefcbf, #f6e05e); }}
        .score-low {{ background: linear-gradient(90deg, #fed7d7, #fc8181); }}

        .auto-applied {{
            border-left: 4px solid #48bb78 !important;
        }}

        /* Sortable indicators */
        .sort-asc::after {{
            content: "▲";
            color: #667eea;
            margin-left: 4px;
            font-size: 10px;
        }}

        .sort-desc::after {{
            content: "▼";
            color: #667eea;
            margin-left: 4px;
            font-size: 10px;
        }}

        /* Links */
        a {{
            color: #667eea;
            text-decoration: none;
            font-weight: 600;
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 0.3px;
            transition: color 0.2s;
        }}

        a:hover {{
            color: #764ba2;
        }}

        /* Status badges */
        .status-badge {{
            padding: 2px 6px;
            border-radius: 4px;
            font-size: 10px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.3px;
        }}

        .status-true {{
            background: #c6f6d5;
            color: #22543d;
        }}

        .status-false {{
            background: #fed7d7;
            color: #742a2a;
        }}

        .status-none {{
            background: #e2e8f0;
            color: #4a5568;
        }}

        /* Scrollbar styling */
        ::-webkit-scrollbar {{
            width: 6px;
        }}

        ::-webkit-scrollbar-track {{
            background: rgba(255, 255, 255, 0.1);
        }}

        ::-webkit-scrollbar-thumb {{
            background: rgba(102, 126, 234, 0.5);
            border-radius: 3px;
        }}

        ::-webkit-scrollbar-thumb:hover {{
            background: rgba(102, 126, 234, 0.7);
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


import json
import os
from datetime import datetime

# # ==== Load Data ====
json_path = r"C:\Users\imjad\Desktop\case study\st\oneClickShell\outputs\run_20250828_131949\job_data_20250828_131949.json"

with open(json_path, "r", encoding="utf-8") as f:
    data = json.load(f)

# ==== Create Filename ====
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

# Get same folder as JSON and create filename
output_dir = os.path.dirname(json_path)
output_path = os.path.join(output_dir, f"summary_crawler_{timestamp}.html")

# ==== Generate HTML ====
generate_html(data, output_path)

