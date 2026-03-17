# report.py

import re

def generate_html(data, filename):

    # ── Statistics ────────────────────────────────────────
    scraped_jobs          = len(data)
    skill_match_count     = sum(1 for j in data if j.get("skillMatch"))
    not_ext_app_count     = sum(1 for j in data if not j.get("extApp"))
    both_count            = sum(1 for j in data if j.get("skillMatch") and not j.get("extApp"))
    location_match_count  = sum(1 for j in data if j.get("locationMatch"))
    experience_match_count= sum(1 for j in data if j.get("experienceMatch"))
    industry_match_count  = sum(1 for j in data if j.get("industryMatch"))
    early_applicant_count = sum(1 for j in data if j.get("earlyApplicant"))
    applied_count         = sum(1 for j in data if j.get("apply_status") == "applied")
    already_applied_count = sum(1 for j in data if j.get("apply_status") == "already_applied")
    remote_count          = sum(1 for j in data if "remote" in str(j.get("work_mode","")).lower() or "wfh" in str(j.get("work_mode","")).lower())
    hybrid_count          = sum(1 for j in data if "hybrid" in str(j.get("work_mode","")).lower())

    # Grade distribution (SmartScorer)
    grade_a = sum(1 for j in data if (j.get("total_score") or 0) >= 80)
    grade_b = sum(1 for j in data if 65 <= (j.get("total_score") or 0) < 80)
    grade_c = sum(1 for j in data if 50 <= (j.get("total_score") or 0) < 65)
    grade_df= sum(1 for j in data if (j.get("total_score") or 0) < 50)
    fire_count = sum(1 for j in data if "Immediately" in str(j.get("apply_priority","")))

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Job Crawler Report</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "Segoe UI", Roboto, sans-serif; background: #F5F5F7; min-height: 100vh; padding: 20px; color: #1D1D1F; }}
        .main-container {{ max-width: 1700px; margin: 0 auto; background: #FFFFFF; border-radius: 18px; box-shadow: 0 4px 20px rgba(0,0,0,0.08); overflow: hidden; }}
        .header {{ background: #FFFFFF; padding: 28px 36px; border-bottom: 1px solid #D2D2D7; }}
        .header-content {{ display: flex; align-items: center; justify-content: space-between; }}
        .header-left {{ display: flex; align-items: center; gap: 20px; }}
        .logo {{ height: 44px; }}
        .header-title {{ font-size: 32px; font-weight: 600; color: #1D1D1F; letter-spacing: -0.5px; }}
        .header-stats {{ display: flex; gap: 10px; flex-wrap: wrap; align-items: center; }}
        .stat-badge {{ background: #F5F5F7; padding: 8px 16px; border-radius: 20px; font-size: 14px; font-weight: 500; color: #1D1D1F; }}
        .stat-badge strong {{ color: #007AFF; font-weight: 600; }}
        .stat-badge.green strong {{ color: #34C759; }}
        .stat-badge.orange strong {{ color: #FF9500; }}
        .stat-badge.red strong {{ color: #FF3B30; }}
        .content {{ display: flex; height: calc(100vh - 180px); position: relative; overflow: hidden; }}
        .sidebar {{ width: 300px; min-width: 200px; max-width: 520px; border-right: 1px solid #D2D2D7; overflow-y: auto; background: #FBFBFD; flex-shrink: 0; transition: width 0.25s ease, min-width 0.25s ease, opacity 0.2s ease; position: relative; }}
        /* Resize handle */
        .resize-handle {{ width: 6px; background: transparent; cursor: col-resize; flex-shrink: 0; position: relative; z-index: 20; transition: background 0.2s; }}
        .resize-handle:hover, .resize-handle.dragging {{ background: #007AFF; }}
        .resize-handle::after {{ content: ''; position: absolute; top: 50%; left: 50%; transform: translate(-50%,-50%); width: 2px; height: 40px; background: #D2D2D7; border-radius: 2px; transition: background 0.2s; }}
        .resize-handle:hover::after, .resize-handle.dragging::after {{ background: #007AFF; }}
        /* Sidebar toggle button — sits in a sticky top bar inside the sidebar */
        .sidebar-toggle {{ width: 28px; height: 28px; border-radius: 50%; background: #FFFFFF; border: 1px solid #D2D2D7; box-shadow: 0 2px 6px rgba(0,0,0,0.1); cursor: pointer; display: flex; align-items: center; justify-content: center; font-size: 12px; transition: all 0.2s ease; color: #86868B; }}
        .sidebar-toggle:hover {{ background: #007AFF; color: #FFFFFF; border-color: #007AFF; }}
        /* Float button: shown in header when sidebar is collapsed — controlled via JS inline style */
        .sidebar-section {{ padding: 20px; border-bottom: 1px solid #E5E5EA; }}
        .section-title {{ font-size: 12px; font-weight: 700; text-transform: uppercase; color: #86868B; margin-bottom: 14px; letter-spacing: 0.6px; }}
        .quick-filters {{ display: flex; flex-direction: column; gap: 7px; }}
        .quick-filter-btn {{ padding: 12px 14px; border: 1px solid #D2D2D7; background: #FFFFFF; border-radius: 10px; cursor: pointer; font-weight: 500; font-size: 14px; color: #1D1D1F; transition: all 0.2s ease; display: flex; align-items: center; justify-content: space-between; text-align: left; }}
        .quick-filter-btn:hover {{ border-color: #007AFF; background: #F5F8FF; }}
        .quick-filter-btn.active {{ background: #007AFF; color: #FFFFFF; border-color: #007AFF; box-shadow: 0 2px 8px rgba(0,122,255,0.3); }}
        .filter-count {{ background: rgba(0,0,0,0.06); padding: 3px 9px; border-radius: 10px; font-size: 12px; font-weight: 700; }}
        .quick-filter-btn.active .filter-count {{ background: rgba(255,255,255,0.25); color: #FFFFFF; }}
        .filter-group {{ margin-bottom: 14px; }}
        .filter-label {{ font-weight: 600; font-size: 13px; color: #1D1D1F; margin-bottom: 8px; display: block; }}
        .work-mode-group {{ display: flex; flex-direction: column; gap: 7px; }}
        .work-mode-btn {{ padding: 11px 13px; border: 1px solid #D2D2D7; background: #FFFFFF; border-radius: 10px; cursor: pointer; font-size: 13px; font-weight: 500; transition: all 0.2s ease; display: flex; align-items: center; justify-content: space-between; color: #1D1D1F; }}
        .work-mode-btn:hover {{ border-color: #007AFF; background: #F5F8FF; }}
        .work-mode-btn.active {{ background: #007AFF; color: #FFFFFF; border-color: #007AFF; }}
        .work-mode-btn.active .filter-count {{ background: rgba(255,255,255,0.25); color: #FFFFFF; }}
        .toggle-group {{ display: flex; gap: 7px; }}
        .toggle-btn {{ flex: 1; padding: 9px 10px; border: 1px solid #D2D2D7; background: #FFFFFF; border-radius: 8px; cursor: pointer; font-size: 13px; font-weight: 500; transition: all 0.2s ease; text-align: center; color: #1D1D1F; }}
        .toggle-btn:hover {{ border-color: #007AFF; background: #F5F8FF; }}
        .toggle-btn.active {{ background: #007AFF; color: #FFFFFF; border-color: #007AFF; }}
        .stats-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }}
        .stat-card {{ background: #FFFFFF; padding: 12px; border-radius: 10px; border: 1px solid #E5E5EA; }}
        .stat-value {{ font-size: 24px; font-weight: 600; color: #007AFF; }}
        .stat-value.green {{ color: #34C759; }}
        .stat-label {{ font-size: 11px; color: #86868B; margin-top: 3px; font-weight: 500; }}
        .grade-bar {{ display: flex; gap: 6px; margin-top: 8px; }}
        .grade-pill {{ flex:1; text-align:center; padding: 6px 4px; border-radius: 8px; font-size: 13px; font-weight: 700; }}
        .grade-a {{ background: rgba(52,199,89,0.15); color: #248A3D; }}
        .grade-b {{ background: rgba(255,204,0,0.2); color: #996300; }}
        .grade-c {{ background: rgba(255,149,0,0.15); color: #C0500A; }}
        .grade-df {{ background: rgba(255,59,48,0.1); color: #FF3B30; }}
        .link-opener {{ background: #FFFFFF; padding: 14px; border-radius: 10px; border: 1px solid #E5E5EA; }}
        .range-inputs {{ display: flex; gap: 8px; margin-bottom: 10px; }}
        .range-input {{ flex: 1; }}
        .range-input label {{ font-size: 12px; color: #86868B; display: block; margin-bottom: 5px; font-weight: 500; }}
        .range-input input {{ width: 100%; padding: 9px 10px; border: 1px solid #D2D2D7; border-radius: 8px; font-size: 14px; background: #FFFFFF; color: #1D1D1F; }}
        .range-input input:focus {{ outline: none; border-color: #007AFF; }}
        .open-btn {{ width: 100%; padding: 11px; background: #007AFF; color: #FFFFFF; border: none; border-radius: 10px; font-weight: 600; font-size: 14px; cursor: pointer; transition: all 0.2s ease; }}
        .open-btn:hover {{ background: #0051D5; }}
        .job-section {{ flex: 1; overflow: auto; padding: 18px; min-width: 0; position: relative; }}
        .table-controls {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; padding: 12px 16px; background: #FBFBFD; border-radius: 10px; border: 1px solid #E5E5EA; }}
        .visible-count {{ font-size: 14px; color: #86868B; font-weight: 500; }}
        .visible-count strong {{ color: #007AFF; font-size: 20px; font-weight: 600; }}
        .reset-btn {{ padding: 7px 14px; background: #FFFFFF; border: 1px solid #D2D2D7; border-radius: 8px; cursor: pointer; font-weight: 600; font-size: 13px; transition: all 0.2s ease; color: #1D1D1F; }}
        .reset-btn:hover {{ border-color: #007AFF; color: #007AFF; }}
        .job-table {{ width: 100%; border-collapse: collapse; background: #FFFFFF; border-radius: 12px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.06); }}
        .job-table thead {{ background: #FBFBFD; position: sticky; top: 0; z-index: 10; }}
        .job-table th {{ padding: 12px 10px; font-size: 12px; font-weight: 700; color: #1D1D1F; text-align: left; cursor: pointer; user-select: none; white-space: nowrap; border-bottom: 1px solid #E5E5EA; text-transform: uppercase; letter-spacing: 0.3px; }}
        .job-table th:hover {{ background: #F5F5F7; }}
        .job-table th.sortable::after {{ content: " ⇅"; opacity: 0.3; font-size: 10px; }}
        .job-table th.sort-asc::after {{ content: " ↑"; opacity: 1; color: #007AFF; }}
        .job-table th.sort-desc::after {{ content: " ↓"; opacity: 1; color: #007AFF; }}
        .job-table td {{ padding: 12px 10px; font-size: 13px; border-bottom: 1px solid #F5F5F7; color: #1D1D1F; vertical-align: middle; }}
        .job-table tbody tr.main-row {{ transition: background 0.15s ease; cursor: pointer; }}
        .job-table tbody tr.main-row:hover {{ background: #F5F8FF !important; }}
        .score-excellent {{ background: linear-gradient(90deg, rgba(52,199,89,0.07) 0%, #FFFFFF 60%); }}
        .score-good {{ background: linear-gradient(90deg, rgba(255,204,0,0.07) 0%, #FFFFFF 60%); }}
        .score-moderate {{ background: linear-gradient(90deg, rgba(255,149,0,0.06) 0%, #FFFFFF 60%); }}
        .score-poor {{ background: linear-gradient(90deg, rgba(255,59,48,0.05) 0%, #FFFFFF 60%); }}
        /* Detail row */
        .detail-row td {{ padding: 0; background: #FAFAFA; border-bottom: 2px solid #E5E5EA; }}
        .detail-content {{ padding: 16px 20px; display: none; }}
        .detail-content.open {{ display: flex; gap: 24px; flex-wrap: wrap; }}
        .detail-section {{ flex: 1; min-width: 180px; }}
        .detail-section h4 {{ font-size: 11px; font-weight: 700; color: #86868B; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 10px; }}
        .breakdown-grid {{ display: flex; flex-direction: column; gap: 6px; }}
        .breakdown-row {{ display: flex; align-items: center; gap: 8px; }}
        .breakdown-label {{ font-size: 12px; color: #1D1D1F; width: 130px; flex-shrink: 0; }}
        .breakdown-bar-bg {{ flex: 1; height: 6px; background: #E5E5EA; border-radius: 3px; overflow: hidden; }}
        .breakdown-bar-fill {{ height: 100%; border-radius: 3px; background: #007AFF; transition: width 0.4s ease; }}
        .breakdown-val {{ font-size: 12px; font-weight: 700; color: #1D1D1F; width: 36px; text-align: right; }}
        .flags-list {{ display: flex; flex-direction: column; gap: 5px; }}
        .flag-item {{ font-size: 12px; color: #1D1D1F; padding: 5px 10px; background: #F5F5F7; border-radius: 6px; line-height: 1.4; }}
        .flag-item.warn {{ background: rgba(255,149,0,0.08); color: #C0500A; }}
        .flag-item.good {{ background: rgba(52,199,89,0.08); color: #248A3D; }}
        .salary-pill {{ display: inline-block; padding: 6px 14px; background: rgba(52,199,89,0.1); color: #248A3D; border-radius: 8px; font-size: 13px; font-weight: 600; }}
        .missing-skills {{ display: flex; flex-wrap: wrap; gap: 5px; }}
        .skill-tag {{ padding: 4px 10px; background: rgba(255,59,48,0.08); color: #FF3B30; border-radius: 6px; font-size: 12px; font-weight: 500; }}
        /* Badges */
        .match-icon {{ display: inline-block; width: 20px; height: 20px; border-radius: 50%; text-align: center; line-height: 20px; font-size: 11px; font-weight: 700; }}
        .match-true {{ background: #34C759; color: #FFFFFF; }}
        .match-false {{ background: #E5E5EA; color: #86868B; }}
        .work-mode-badge {{ display: inline-block; padding: 4px 10px; border-radius: 10px; font-size: 12px; font-weight: 600; }}
        .wfh {{ background: rgba(0,122,255,0.1); color: #007AFF; }}
        .hybrid {{ background: rgba(255,149,0,0.1); color: #FF9500; }}
        .office {{ background: rgba(134,134,139,0.1); color: #86868B; }}
        .score-cell {{ display: flex; flex-direction: column; align-items: flex-start; gap: 3px; }}
        .score-num {{ font-size: 18px; font-weight: 700; }}
        .score-grade {{ font-size: 11px; font-weight: 600; opacity: 0.75; }}
        .score-a {{ color: #34C759; }}
        .score-b {{ color: #FFCC00; }}
        .score-c {{ color: #FF9500; }}
        .score-df {{ color: #FF3B30; }}
        .priority-badge {{ display: inline-block; padding: 4px 10px; border-radius: 8px; font-size: 12px; font-weight: 600; white-space: nowrap; }}
        .priority-fire {{ background: rgba(255,59,48,0.1); color: #FF3B30; }}
        .priority-today {{ background: rgba(52,199,89,0.1); color: #248A3D; }}
        .priority-week {{ background: rgba(0,122,255,0.1); color: #007AFF; }}
        .priority-skip {{ background: #F5F5F7; color: #86868B; }}
        .apply-badge {{ display: inline-block; padding: 4px 10px; border-radius: 10px; font-size: 12px; font-weight: 600; }}
        .apply-applied {{ background: rgba(52,199,89,0.15); color: #248A3D; }}
        .apply-already {{ background: rgba(0,122,255,0.1); color: #007AFF; }}
        .apply-failed {{ background: rgba(255,59,48,0.1); color: #FF3B30; }}
        .apply-pending {{ background: rgba(134,134,139,0.08); color: #86868B; }}
        .job-link {{ color: #007AFF; text-decoration: none; font-weight: 600; padding: 5px 10px; border-radius: 7px; transition: all 0.2s ease; display: inline-block; }}
        .job-link:hover {{ background: #F5F8FF; }}
        .expand-icon {{ color: #86868B; font-size: 11px; transition: transform 0.2s ease; display: inline-block; }}
        .expand-icon.open {{ transform: rotate(90deg); }}
        ::-webkit-scrollbar {{ width: 8px; height: 8px; }}
        ::-webkit-scrollbar-track {{ background: #F5F5F7; }}
        ::-webkit-scrollbar-thumb {{ background: #D2D2D7; border-radius: 4px; }}
        ::-webkit-scrollbar-thumb:hover {{ background: #86868B; }}
    </style>
</head>
<body>
<div class="main-container">
    <div class="header">
        <div class="header-content">
            <div class="header-left">
                <button id="sidebarToggleBtn" onclick="toggleSidebar()" style="width:36px;height:36px;border-radius:50%;background:#F5F5F7;border:1px solid #D2D2D7;cursor:pointer;font-size:16px;display:flex;align-items:center;justify-content:center;flex-shrink:0;transition:all 0.2s;" title="Toggle sidebar">◀</button>
                <img src="https://i.ibb.co/9mPXLmSN/logo-removebg-preview.png" class="logo" alt="Logo">
                <div class="header-title">Job Crawler</div>
            </div>
            <div class="header-stats">
                <div class="stat-badge"><strong>{scraped_jobs}</strong> Jobs</div>
                <div class="stat-badge orange"><strong>{fire_count}</strong> 🔥 Apply Now</div>
                <div class="stat-badge green"><strong>{grade_a}</strong> Grade A</div>
                <div class="stat-badge"><strong>{grade_b}</strong> Grade B</div>
                <div class="stat-badge green"><strong>{applied_count}</strong> Applied</div>
                <div class="stat-badge"><strong>{early_applicant_count}</strong> Early</div>
            </div>
        </div>
    </div>
    <div class="content">
        <div class="sidebar" id="sidebar">

            <div class="sidebar-section">
                <div class="section-title">Quick Filters</div>
                <div class="quick-filters">
                    <button class="quick-filter-btn" onclick="applyQuickFilter('fire')">
                        <span>🔥 Apply Immediately</span><span class="filter-count">{fire_count}</span>
                    </button>
                    <button class="quick-filter-btn" onclick="applyQuickFilter('grade_a')">
                        <span>🏅 Grade A (≥80)</span><span class="filter-count">{grade_a}</span>
                    </button>
                    <button class="quick-filter-btn" onclick="applyQuickFilter('grade_ab')">
                        <span>⭐ Grade A+B (≥65)</span><span class="filter-count">{grade_a + grade_b}</span>
                    </button>
                    <button class="quick-filter-btn" onclick="applyQuickFilter('best')">
                        <span>🎯 Best Matches</span><span class="filter-count">{both_count}</span>
                    </button>
                    <button class="quick-filter-btn" onclick="applyQuickFilter('applied')">
                        <span>✅ Applied</span><span class="filter-count">{applied_count + already_applied_count}</span>
                    </button>
                    <button class="quick-filter-btn" onclick="applyQuickFilter('skill')">
                        <span>💼 Skill Match</span><span class="filter-count">{skill_match_count}</span>
                    </button>
                    <button class="quick-filter-btn" onclick="applyQuickFilter('early')">
                        <span>⚡ Early Applicant</span><span class="filter-count">{early_applicant_count}</span>
                    </button>
                    <button class="quick-filter-btn" onclick="applyQuickFilter('remote')">
                        <span>🏠 Remote Only</span><span class="filter-count">{remote_count}</span>
                    </button>
                </div>
            </div>

            <div class="sidebar-section">
                <div class="section-title">Grade Distribution</div>
                <div class="grade-bar">
                    <div class="grade-pill grade-a">A<br><small>{grade_a}</small></div>
                    <div class="grade-pill grade-b">B<br><small>{grade_b}</small></div>
                    <div class="grade-pill grade-c">C<br><small>{grade_c}</small></div>
                    <div class="grade-pill grade-df">D/F<br><small>{grade_df}</small></div>
                </div>
            </div>

            <div class="sidebar-section">
                <div class="section-title">Work Mode</div>
                <div class="work-mode-group">
                    <button class="work-mode-btn" id="workModeRemote" onclick="toggleWorkMode('remote')">
                        <span>🏠 Remote</span><span class="filter-count">{remote_count}</span>
                    </button>
                    <button class="work-mode-btn" id="workModeHybrid" onclick="toggleWorkMode('hybrid')">
                        <span>🔄 Hybrid</span><span class="filter-count">{hybrid_count}</span>
                    </button>
                    <button class="work-mode-btn" id="workModeBoth" onclick="toggleWorkMode('both')">
                        <span>✨ Remote or Hybrid</span><span class="filter-count">{remote_count + hybrid_count}</span>
                    </button>
                </div>
            </div>

            <div class="sidebar-section">
                <div class="section-title">Advanced Filters</div>
                <div class="filter-group">
                    <span class="filter-label">External Application</span>
                    <div class="toggle-group">
                        <button class="toggle-btn" id="extAppYes" onclick="toggleFilter('extApp', 'yes')">Yes</button>
                        <button class="toggle-btn" id="extAppNo" onclick="toggleFilter('extApp', 'no')">No</button>
                    </div>
                </div>
                <div class="filter-group">
                    <span class="filter-label">Skill Match</span>
                    <div class="toggle-group">
                        <button class="toggle-btn" id="skillMatchYes" onclick="toggleFilter('skillMatch', 'yes')">Yes</button>
                        <button class="toggle-btn" id="skillMatchNo" onclick="toggleFilter('skillMatch', 'no')">No</button>
                    </div>
                </div>
                <div class="filter-group">
                    <span class="filter-label">Location Match</span>
                    <div class="toggle-group">
                        <button class="toggle-btn" id="locationMatchYes" onclick="toggleFilter('locationMatch', 'yes')">Yes</button>
                        <button class="toggle-btn" id="locationMatchNo" onclick="toggleFilter('locationMatch', 'no')">No</button>
                    </div>
                </div>
                <div class="filter-group">
                    <span class="filter-label">Experience Match</span>
                    <div class="toggle-group">
                        <button class="toggle-btn" id="experienceMatchYes" onclick="toggleFilter('experienceMatch', 'yes')">Yes</button>
                        <button class="toggle-btn" id="experienceMatchNo" onclick="toggleFilter('experienceMatch', 'no')">No</button>
                    </div>
                </div>
                <div class="filter-group">
                    <span class="filter-label">Industry Match</span>
                    <div class="toggle-group">
                        <button class="toggle-btn" id="industryMatchYes" onclick="toggleFilter('industryMatch', 'yes')">Yes</button>
                        <button class="toggle-btn" id="industryMatchNo" onclick="toggleFilter('industryMatch', 'no')">No</button>
                    </div>
                </div>
                <div class="filter-group">
                    <span class="filter-label">Auto-Applied</span>
                    <div class="toggle-group">
                        <button class="toggle-btn" id="appliedYes" onclick="toggleFilter('applied', 'yes')">Yes</button>
                        <button class="toggle-btn" id="appliedNo" onclick="toggleFilter('applied', 'no')">No</button>
                    </div>
                </div>
            </div>

            <div class="sidebar-section">
                <div class="section-title">Statistics</div>
                <div class="stats-grid">
                    <div class="stat-card"><div class="stat-value green">{applied_count}</div><div class="stat-label">Applied</div></div>
                    <div class="stat-card"><div class="stat-value">{skill_match_count}</div><div class="stat-label">Skill Match</div></div>
                    <div class="stat-card"><div class="stat-value">{not_ext_app_count}</div><div class="stat-label">No Ext App</div></div>
                    <div class="stat-card"><div class="stat-value">{location_match_count}</div><div class="stat-label">Location</div></div>
                    <div class="stat-card"><div class="stat-value">{experience_match_count}</div><div class="stat-label">Experience</div></div>
                    <div class="stat-card"><div class="stat-value">{early_applicant_count}</div><div class="stat-label">Early</div></div>
                </div>
            </div>

            <div class="sidebar-section">
                <div class="section-title">Bulk Actions</div>
                <div class="link-opener">
                    <div class="range-inputs">
                        <div class="range-input"><label>Start</label><input type="number" id="startIdx" value="0" min="0"></div>
                        <div class="range-input"><label>End</label><input type="number" id="endIdx" value="20" min="0"></div>
                    </div>
                    <button class="open-btn" onclick="openJobLinks()">Open Selected Jobs</button>
                </div>
            </div>

        </div><!-- /sidebar -->
        <div class="resize-handle" id="resizeHandle"></div>
        <div class="job-section">
            <div class="table-controls">
                <div class="visible-count">Showing <strong id="visibleCount">0</strong> of {scraped_jobs} jobs</div>
                <button class="reset-btn" onclick="resetFilters()">Reset Filters</button>
            </div>
            <table class="job-table" id="jobTable">
                <thead>
                    <tr>
                        <th style="width:36px;"></th>
                        <th style="width:40px;">#</th>
                        <th class="sortable" onclick="sortTable(2)" style="min-width:200px;">Job Title</th>
                        <th class="sortable" onclick="sortTable(3)" style="min-width:140px;">Company</th>
                        <th class="sortable" onclick="sortTable(4)" style="width:90px;">Posted</th>
                        <th style="min-width:110px;">Location</th>
                        <th style="width:100px;">Mode</th>
                        <th class="sortable" onclick="sortTable(7)" style="width:85px;">Applicants</th>
                        <th style="width:60px;">Link</th>
                        <th style="width:44px;">Ext</th>
                        <th style="width:44px;">Skill</th>
                        <th style="width:44px;">Loc</th>
                        <th style="width:44px;">Exp</th>
                        <th style="width:44px;">Ind</th>
                        <th style="width:44px;">Early</th>
                        <th class="sortable" onclick="sortTable(15)" style="width:80px;">Score</th>
                        <th style="width:130px;">Priority</th>
                        <th style="width:90px;">Applied</th>
                    </tr>
                </thead>
                <tbody>"""

    for idx, job in enumerate(data, 1):
        total_score = job.get("total_score")
        score_val   = total_score if total_score is not None else ((job.get("score") or 0) * 100)

        # Row colour
        if score_val >= 80:
            row_class       = "score-excellent"
            score_col_class = "score-a"
            grade_short     = "A"
        elif score_val >= 65:
            row_class       = "score-good"
            score_col_class = "score-b"
            grade_short     = "B"
        elif score_val >= 50:
            row_class       = "score-moderate"
            score_col_class = "score-c"
            grade_short     = "C"
        else:
            row_class       = "score-poor"
            score_col_class = "score-df"
            grade_short     = "D/F"

        # Work mode
        work_mode = str(job.get("work_mode", "")).lower()
        if "remote" in work_mode or "wfh" in work_mode:
            wm_class, wm_display = "wfh", "🏠 Remote"
        elif "hybrid" in work_mode:
            wm_class, wm_display = "hybrid", "🔄 Hybrid"
        else:
            wm_class, wm_display = "office", "🏢 Office"

        def fmt_match(val):
            return '<span class="match-icon match-true">✓</span>' if val else '<span class="match-icon match-false">✗</span>'

        # Apply status
        apply_status = job.get("apply_status", "")
        if apply_status == "applied":
            apply_badge = '<span class="apply-badge apply-applied">✓ Applied</span>'
            apply_data  = "applied"
        elif apply_status == "already_applied":
            apply_badge = '<span class="apply-badge apply-already">Already</span>'
            apply_data  = "already_applied"
        elif apply_status:
            apply_badge = f'<span class="apply-badge apply-failed">{str(apply_status)[:10]}</span>'
            apply_data  = "failed"
        else:
            apply_badge = '<span class="apply-badge apply-pending">—</span>'
            apply_data  = "none"

        # Apply priority badge
        priority = job.get("apply_priority", "")
        if "Immediately" in priority:
            p_class = "priority-fire"
        elif "Today" in priority:
            p_class = "priority-today"
        elif "Week" in priority:
            p_class = "priority-week"
        else:
            p_class = "priority-skip"
        priority_badge = f'<span class="priority-badge {p_class}">{priority}</span>' if priority else "—"

        # Applicants
        applicants_text = job.get("applicants_text", "")
        applicants_num  = 0
        if applicants_text:
            m = re.search(r'(\d+)', applicants_text)
            if m:
                applicants_num = int(m.group(1))

        score_display = f"{score_val:.0f}" if score_val else "N/A"

        # ── Score breakdown bars ──────────────────────────
        breakdown  = job.get("score_breakdown") or {}
        bd_html    = ""
        bd_labels  = {
            "skill_match":         "Skill Match",
            "semantic_similarity": "Semantic",
            "naukri_v3_signals":   "Naukri v3",
            "experience_fit":      "Experience",
            "location_mode":       "Location",
            "competition_quality": "Competition",
        }
        for key, label in bd_labels.items():
            val = breakdown.get(key, 0)
            bar_color = "#34C759" if val >= 70 else ("#FF9500" if val >= 40 else "#FF3B30")
            bd_html += f"""<div class="breakdown-row">
                <span class="breakdown-label">{label}</span>
                <div class="breakdown-bar-bg"><div class="breakdown-bar-fill" style="width:{val}%;background:{bar_color};"></div></div>
                <span class="breakdown-val">{val:.0f}</span>
            </div>"""

        # ── Flags ─────────────────────────────────────────
        flags     = job.get("score_flags") or []
        flags_html = ""
        for f in flags:
            if "Missing" in f or "gap" in f or "High competition" in f or "Stale" in f:
                cls = "warn"
            elif "MNC" in f or "Salary" in f:
                cls = "good"
            else:
                cls = ""
            flags_html += f'<div class="flag-item {cls}">{f}</div>'
        if not flags_html:
            flags_html = '<div class="flag-item">No flags</div>'

        # ── Missing skills ────────────────────────────────
        missing    = job.get("missing_skills") or []
        miss_html  = "".join(f'<span class="skill-tag">{s}</span>' for s in missing) or "<span style='color:#86868B;font-size:12px'>None</span>"

        # ── Salary ────────────────────────────────────────
        salary     = job.get("salary_insight") or ""
        sal_html   = f'<div class="salary-pill">{salary}</div>' if salary else '<span style="color:#86868B;font-size:12px">Not disclosed</span>'

        row_id     = f"row_{idx}"
        detail_id  = f"detail_{idx}"

        html_content += f"""
                    <tr class="main-row {row_class}"
                        id="{row_id}"
                        data-extapp="{str(job.get('extApp', False)).lower()}"
                        data-skillmatch="{str(job.get('skillMatch', False)).lower()}"
                        data-earlyapp="{str(job.get('earlyApplicant', False)).lower()}"
                        data-locationmatch="{str(job.get('locationMatch', False)).lower()}"
                        data-experiencematch="{str(job.get('experienceMatch', False)).lower()}"
                        data-industrymatch="{str(job.get('industryMatch', False)).lower()}"
                        data-workmode="{work_mode}"
                        data-score="{score_val:.1f}"
                        data-applicants="{applicants_num}"
                        data-applystatus="{apply_data}"
                        data-grade="{grade_short}"
                        data-priority="{priority}"
                        onclick="toggleDetail('{detail_id}', this)">
                        <td><span class="expand-icon" id="icon_{idx}">▶</span></td>
                        <td>{idx}</td>
                        <td><strong>{job.get("Job Title", "")}</strong></td>
                        <td>{job.get("Company Name", "")}</td>
                        <td>{job.get("age", "")}</td>
                        <td>{job.get("location", "")}</td>
                        <td><span class="work-mode-badge {wm_class}">{wm_display}</span></td>
                        <td>{applicants_text}</td>
                        <td><a href="{job.get("URL", "#")}" target="_blank" class="job-link" onclick="event.stopPropagation()">View</a></td>
                        <td>{fmt_match(not job.get("extApp", True))}</td>
                        <td>{fmt_match(job.get("skillMatch", False))}</td>
                        <td>{fmt_match(job.get("locationMatch", False))}</td>
                        <td>{fmt_match(job.get("experienceMatch", False))}</td>
                        <td>{fmt_match(job.get("industryMatch", False))}</td>
                        <td>{fmt_match(job.get("earlyApplicant", False))}</td>
                        <td>
                            <div class="score-cell">
                                <span class="score-num {score_col_class}">{score_display}</span>
                                <span class="score-grade {score_col_class}">{grade_short}</span>
                            </div>
                        </td>
                        <td>{priority_badge}</td>
                        <td>{apply_badge}</td>
                    </tr>
                    <tr class="detail-row" id="{detail_id}">
                        <td colspan="18">
                            <div class="detail-content" id="content_{idx}">
                                <div class="detail-section">
                                    <h4>Score Breakdown</h4>
                                    <div class="breakdown-grid">{bd_html}</div>
                                </div>
                                <div class="detail-section">
                                    <h4>Flags &amp; Insights</h4>
                                    <div class="flags-list">{flags_html}</div>
                                </div>
                                <div class="detail-section" style="min-width:160px;">
                                    <h4>Missing Skills</h4>
                                    <div class="missing-skills">{miss_html}</div>
                                    <br>
                                    <h4>Salary</h4>
                                    {sal_html}
                                </div>
                            </div>
                        </td>
                    </tr>"""

    html_content += """
                </tbody>
            </table>
        </div><!-- /job-section -->
    </div><!-- /content -->
</div><!-- /main-container -->

<script>
    let filters = {
        extApp: null, skillMatch: null, locationMatch: null,
        experienceMatch: null, industryMatch: null, earlyApplicant: null,
        workMode: null, applied: null, grade: null, priority: null,
        activeQuickFilter: null
    };

    document.addEventListener("DOMContentLoaded", () => { applyFilters(); });

    function toggleDetail(detailId, row) {
        const idx = detailId.split('_')[1];
        const content = document.getElementById('content_' + idx);
        const icon    = document.getElementById('icon_' + idx);
        const isOpen  = content.classList.contains('open');
        content.classList.toggle('open', !isOpen);
        icon.classList.toggle('open', !isOpen);
    }

    function applyQuickFilter(type) {
        const clickedBtn = event.target.closest('.quick-filter-btn');
        if (filters.activeQuickFilter === type) { resetFilters(); return; }
        filters = { extApp:null, skillMatch:null, locationMatch:null, experienceMatch:null,
                    industryMatch:null, earlyApplicant:null, workMode:null, applied:null,
                    grade:null, priority:null, activeQuickFilter: type };
        document.querySelectorAll('.quick-filter-btn').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.toggle-btn').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.work-mode-btn').forEach(b => b.classList.remove('active'));
        clickedBtn.classList.add('active');
        switch(type) {
            case 'fire':    filters.priority = 'fire'; break;
            case 'grade_a': filters.grade = 'A'; break;
            case 'grade_ab':filters.grade = 'AB'; break;
            case 'best':    filters.skillMatch = 'yes'; filters.extApp = 'no'; break;
            case 'applied': filters.applied = 'yes'; break;
            case 'skill':   filters.skillMatch = 'yes'; break;
            case 'early':   filters.earlyApplicant = 'yes'; break;
            case 'remote':  filters.workMode = 'remote'; break;
        }
        applyFilters();
    }

    function toggleFilter(filterName, value) {
        const btnId = filterName + (value === 'yes' ? 'Yes' : 'No');
        const btn   = document.getElementById(btnId);
        filters.activeQuickFilter = null;
        document.querySelectorAll('.quick-filter-btn').forEach(b => b.classList.remove('active'));
        if (filters[filterName] === value) { filters[filterName] = null; btn.classList.remove('active'); }
        else {
            filters[filterName] = value;
            const sib = document.getElementById(filterName + (value === 'yes' ? 'No' : 'Yes'));
            if (sib) sib.classList.remove('active');
            btn.classList.add('active');
        }
        applyFilters();
    }

    function toggleWorkMode(mode) {
        const btn = document.getElementById('workMode' + mode.charAt(0).toUpperCase() + mode.slice(1));
        document.querySelectorAll('.work-mode-btn').forEach(b => b.classList.remove('active'));
        if (filters.workMode === mode) { filters.workMode = null; }
        else { filters.workMode = mode; btn.classList.add('active'); }
        applyFilters();
    }

    function applyFilters() {
        let visible = 0;
        document.querySelectorAll("#jobTable tbody tr.main-row").forEach(row => {
            let show = true;
            const wm    = row.getAttribute("data-workmode").toLowerCase();
            const grade = row.getAttribute("data-grade");
            const prio  = row.getAttribute("data-priority");
            const score = parseFloat(row.getAttribute("data-score")) || 0;

            if (filters.extApp !== null) {
                const v = row.getAttribute("data-extapp") === "true";
                if (filters.extApp === 'yes' && !v) show = false;
                if (filters.extApp === 'no'  &&  v) show = false;
            }
            if (filters.skillMatch !== null) {
                const v = row.getAttribute("data-skillmatch") === "true";
                if (filters.skillMatch === 'yes' && !v) show = false;
                if (filters.skillMatch === 'no'  &&  v) show = false;
            }
            if (filters.locationMatch !== null) {
                const v = row.getAttribute("data-locationmatch") === "true";
                if (filters.locationMatch === 'yes' && !v) show = false;
                if (filters.locationMatch === 'no'  &&  v) show = false;
            }
            if (filters.experienceMatch !== null) {
                const v = row.getAttribute("data-experiencematch") === "true";
                if (filters.experienceMatch === 'yes' && !v) show = false;
                if (filters.experienceMatch === 'no'  &&  v) show = false;
            }
            if (filters.industryMatch !== null) {
                const v = row.getAttribute("data-industrymatch") === "true";
                if (filters.industryMatch === 'yes' && !v) show = false;
                if (filters.industryMatch === 'no'  &&  v) show = false;
            }
            if (filters.earlyApplicant === 'yes') {
                if (row.getAttribute("data-earlyapp") !== "true") show = false;
            }
            if (filters.workMode !== null) {
                if (filters.workMode === 'remote' && !wm.includes('remote') && !wm.includes('wfh')) show = false;
                else if (filters.workMode === 'hybrid' && !wm.includes('hybrid')) show = false;
                else if (filters.workMode === 'both' && !wm.includes('remote') && !wm.includes('wfh') && !wm.includes('hybrid')) show = false;
            }
            if (filters.applied !== null) {
                const as_ = row.getAttribute("data-applystatus");
                if (filters.applied === 'yes' && as_ !== 'applied' && as_ !== 'already_applied') show = false;
                if (filters.applied === 'no'  && (as_ === 'applied' || as_ === 'already_applied')) show = false;
            }
            if (filters.grade !== null) {
                if (filters.grade === 'A'  && grade !== 'A') show = false;
                if (filters.grade === 'AB' && grade !== 'A' && grade !== 'B') show = false;
            }
            if (filters.priority === 'fire' && !prio.includes('Immediately')) show = false;

            row.style.display = show ? "" : "none";
            // also hide/show the adjacent detail row
            const detailRow = row.nextElementSibling;
            if (detailRow && detailRow.classList.contains('detail-row')) {
                detailRow.style.display = show ? "" : "none";
            }
            if (show) visible++;
        });
        document.getElementById("visibleCount").innerText = visible;
    }

    function resetFilters() {
        filters = { extApp:null, skillMatch:null, locationMatch:null, experienceMatch:null,
                    industryMatch:null, earlyApplicant:null, workMode:null, applied:null,
                    grade:null, priority:null, activeQuickFilter:null };
        document.querySelectorAll('.toggle-btn, .quick-filter-btn, .work-mode-btn').forEach(b => b.classList.remove('active'));
        applyFilters();
    }

    function openJobLinks() {
        const start = parseInt(document.getElementById("startIdx").value);
        const end   = parseInt(document.getElementById("endIdx").value);
        const rows  = Array.from(document.querySelectorAll("#jobTable tbody tr.main-row")).filter(r => r.style.display !== "none");
        let opened  = 0;
        rows.forEach((row, i) => {
            if (i >= start && i < end) {
                const link = row.querySelector("a.job-link");
                if (link) { window.open(link.href, '_blank'); opened++; }
            }
        });
        if (opened) alert('Opened ' + opened + ' jobs');
    }

    let currentSort = { column: -1, asc: true };
    function sortTable(col) {
        const tbody = document.querySelector("#jobTable tbody");
        // collect main-row + its detail-row as pairs
        const mainRows = Array.from(tbody.querySelectorAll("tr.main-row"));
        const pairs    = mainRows.map(r => [r, r.nextElementSibling]);
        const asc      = currentSort.column === col ? !currentSort.asc : true;
        currentSort    = { column: col, asc: asc };
        pairs.sort((a, b) => {
            const ra = a[0], rb = b[0];
            let av, bv;
            if (col === 4) { av = extractAge(ra.cells[col].innerText); bv = extractAge(rb.cells[col].innerText); }
            else if (col === 7) { av = parseInt(ra.getAttribute("data-applicants")) || 0; bv = parseInt(rb.getAttribute("data-applicants")) || 0; }
            else if (col === 15){ av = parseFloat(ra.getAttribute("data-score")) || 0; bv = parseFloat(rb.getAttribute("data-score")) || 0; }
            else { av = ra.cells[col].innerText.toLowerCase(); bv = rb.cells[col].innerText.toLowerCase(); }
            if (av < bv) return asc ? -1 : 1;
            if (av > bv) return asc ? 1 : -1;
            return 0;
        });
        pairs.forEach(([main, detail]) => { tbody.appendChild(main); if (detail) tbody.appendChild(detail); });
        document.querySelectorAll(".job-table th").forEach(th => th.classList.remove("sort-asc", "sort-desc"));
        document.querySelectorAll(".job-table th")[col].classList.add(asc ? "sort-asc" : "sort-desc");
    }

    function extractAge(text) {
        const m = text.match(/(\d+)/);
        if (!m) return 999;
        const n = parseInt(m[1]);
        const t = text.toLowerCase();
        if (t.includes('hour'))  return n / 24;
        if (t.includes('day'))   return n;
        if (t.includes('week'))  return n * 7;
        if (t.includes('month')) return n * 30;
        return n;
    }

    // ── Sidebar collapse ────────────────────────────────────
    let sidebarOpen = true;
    function toggleSidebar() {
        const sidebar  = document.getElementById('sidebar');
        const handle   = document.getElementById('resizeHandle');
        const btn      = document.getElementById('sidebarToggleBtn');
        sidebarOpen = !sidebarOpen;
        if (sidebarOpen) {
            sidebar.style.width    = '300px';
            sidebar.style.minWidth = '200px';
            sidebar.style.opacity  = '1';
            sidebar.style.overflow = 'hidden auto';
            handle.style.display   = '';
            btn.textContent        = '◀';
            btn.style.background   = '#F5F5F7';
            btn.style.color        = '#1D1D1F';
        } else {
            sidebar.style.width    = '0';
            sidebar.style.minWidth = '0';
            sidebar.style.opacity  = '0';
            sidebar.style.overflow = 'hidden';
            handle.style.display   = 'none';
            btn.textContent        = '▶';
            btn.style.background   = '#007AFF';
            btn.style.color        = '#FFFFFF';
        }
    }

    // ── Sidebar resize ──────────────────────────────────────
    (function() {
        const handle  = document.getElementById('resizeHandle');
        const sidebar = document.getElementById('sidebar');
        let dragging  = false;
        let startX    = 0;
        let startW    = 0;

        handle.addEventListener('mousedown', function(e) {
            dragging = true;
            startX   = e.clientX;
            startW   = sidebar.getBoundingClientRect().width;
            handle.classList.add('dragging');
            document.body.style.cursor = 'col-resize';
            document.body.style.userSelect = 'none';
            e.preventDefault();
        });

        document.addEventListener('mousemove', function(e) {
            if (!dragging) return;
            const delta  = e.clientX - startX;
            const newW   = Math.min(520, Math.max(200, startW + delta));
            sidebar.style.width = newW + 'px';
        });

        document.addEventListener('mouseup', function() {
            if (!dragging) return;
            dragging = false;
            handle.classList.remove('dragging');
            document.body.style.cursor = '';
            document.body.style.userSelect = '';
        });
    })();
</script>
</body>
</html>"""

    with open(filename, "w", encoding="utf-8") as f:
        f.write(html_content)