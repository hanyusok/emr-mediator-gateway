const API_URL = ""; // Root URL since page is served from same host

// Global states
let databaseSchema = {};
let selectedPcode = null;
let selectedPatient = null;

// On document ready
window.addEventListener("DOMContentLoaded", () => {
    fetchSchema();
    fetchWaitlist();
    // Polling waitlist every 10 seconds
    setInterval(fetchWaitlist, 10000);
});

// 1. Fetch Waitlist
function fetchWaitlist() {
    fetch(`${API_URL}/api/waiting`)
        .then(res => res.json())
        .then(data => {
            const waitListEl = document.getElementById("waitlist");
            waitListEl.innerHTML = "";

            if (!data.queue || data.queue.length === 0) {
                waitListEl.innerHTML = `<li style="text-align: center; color: var(--text-muted); padding: 2rem;">Waitlist is currently empty.</li>`;
                return;
            }

            data.queue.forEach(item => {
                const li = document.createElement("li");
                li.className = "waitlist-item";

                const pName = item.pname || (item.patient ? item.patient.pname : `Code: ${item.pcode}`);
                const time = item.visitime || '';
                const extra = item.fin ? `FIN:${item.fin}` : '';

                li.innerHTML = `
                    <div class="patient-summary">
                        <h4>${pName}</h4>
                        <p>${time} ${extra}</p>
                    </div>
                    <div class="waitlist-actions">
                        <span style="color:var(--text-muted);">MTR</span>
                        <button class="delete-btn">삭제</button>
                    </div>
                `;

                // Add click handler to open patient details when the card is clicked
                li.onclick = () => selectPatient(item.pcode);

                // Add click handler specifically to the delete button
                const deleteBtn = li.querySelector(".delete-btn");
                deleteBtn.onclick = (event) => {
                    deleteFromWaitlist(event, item.resid1, pName);
                };

                waitListEl.appendChild(li);
            });
        })
        .catch(err => {
            console.error("Waitlist error:", err);
            document.getElementById("waitlist").innerHTML = `<li style="text-align: center; color: #f87171; padding: 1rem;">Failed to connect to waitlist.</li>`;
        });
}

// 2. Fetch Schema metadata
function fetchSchema() {
    fetch(`${API_URL}/api/schema`)
        .then(res => res.json())
        .then(schema => {
            databaseSchema = schema;
            renderSchemaTree(schema);
        })
        .catch(err => {
            console.error("Schema fetch error:", err);
            document.getElementById("schema-tree").innerHTML = `<div style="text-align: center; color: #f87171; padding: 1rem;">Failed to load database schemas.</div>`;
        });
}

// Render Schema Tree
function renderSchemaTree(schema) {
    const container = document.getElementById("schema-tree");
    container.innerHTML = "";

    Object.keys(schema).forEach(dbName => {
        const dbNode = document.createElement("div");
        dbNode.className = "tree-node";
        dbNode.classList.remove("expanded");

        const dbLabel = document.createElement("div");
        dbLabel.className = "tree-label";
        dbLabel.onclick = () => toggleNode(dbNode);
        
        dbLabel.innerHTML = `
            <svg class="tree-icon" viewBox="0 0 24 24"><path d="M10 6L8.59 7.41 13.17 12l-4.58 4.59L10 18l6-6z"/></svg>
            <svg style="width:1rem;height:1rem;fill:#6366f1" viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z"/></svg>
            <strong>${dbName}.FDB</strong>
        `;
        
        const dbChildren = document.createElement("div");
        dbChildren.className = "tree-children";

        const tables = schema[dbName];
        if (tables.error) {
            dbChildren.innerHTML = `<div style="color:#ef4444;padding:0.25rem 1rem;">${tables.error}</div>`;
        } else {
            Object.keys(tables).forEach(tblName => {
                const tblNode = document.createElement("div");
                tblNode.className = "tree-node";
                tblNode.classList.remove("expanded");
                
                const tblLabel = document.createElement("div");
                tblLabel.className = "tree-label";
                tblLabel.onclick = (e) => {
                    e.stopPropagation();
                    toggleNode(tblNode);
                };

                tblLabel.innerHTML = `
                    <svg class="tree-icon" viewBox="0 0 24 24"><path d="M10 6L8.59 7.41 13.17 12l-4.58 4.59L10 18l6-6z"/></svg>
                    <svg style="width:0.95rem;height:0.95rem;fill:#06b6d4" viewBox="0 0 24 24"><path d="M4 6H2v14c0 1.1.9 2 2 2h14v-2H4V6zm16-4H8c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm0 14H8V4h12v12z"/></svg>
                    <span>${tblName}</span>
                `;

                const tblChildren = document.createElement("div");
                tblChildren.className = "tree-children";

                tables[tblName].forEach(col => {
                    const colDiv = document.createElement("div");
                    colDiv.className = "col-item";
                    colDiv.innerHTML = `
                        <span>${col.column}</span>
                        <span class="col-type">${col.type}(${col.length})</span>
                    `;
                    tblChildren.appendChild(colDiv);
                });

                tblNode.appendChild(tblLabel);
                tblNode.appendChild(tblChildren);
                dbChildren.appendChild(tblNode);
            });
        }

        dbNode.appendChild(dbLabel);
        dbNode.appendChild(dbChildren);
        container.appendChild(dbNode);
    });
}

function toggleNode(node) {
    node.classList.toggle("expanded");
}

// 3. Search Patients
function handleSearchKeyPress(event) {
    if (event.key === "Enter") {
        searchPatients();
    }
}

function searchPatients() {
    const query = document.getElementById("search-query").value.trim();
    let url = `${API_URL}/api/patients?limit=50`;
    
    if (query) {
        if (/^\d+$/.test(query)) {
            url += `&pcode=${query}`;
        } else {
            url += `&pname=${encodeURIComponent(query)}`;
        }
    }

    const tbody = document.getElementById("patient-list");
    tbody.innerHTML = `<tr><td colspan="6" class="empty-placeholder">Searching patient records in database...</td></tr>`;

    fetch(url)
        .then(res => res.json())
        .then(patients => {
            tbody.innerHTML = "";
            if (patients.length === 0) {
                tbody.innerHTML = `<tr><td colspan="6" class="empty-placeholder">No matching patients found.</td></tr>`;
                return;
            }

            patients.forEach(p => {
                const tr = document.createElement("tr");
                tr.onclick = () => selectPatient(p.pcode);
                
                const genderClass = p.sex === "1" || p.sex === "3" ? "gender-male" : "gender-female";
                const genderText = p.sex === "1" || p.sex === "3" ? "M" : "F";
                const birth = p.pbirth || "-";
                
                // Custom styling for decrypted RRN
                let rrnHTML = "";
                if (p.pidnum_decrypted) {
                    rrnHTML = `
                        <span class="rrn-decrypted">
                            <svg viewBox="0 0 24 24"><path d="M18 8h-1V6c0-2.76-2.24-5-5-5S7 3.24 7 6v2H6c-1.1 0-2 .9-2 2v10c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V10c0-1.1-.9-2-2-2zm-6 9c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2zm3.1-9H8.9V6c0-1.71 1.39-3.1 3.1-3.1 1.71 0 3.1 1.39 3.1 3.1v2z"/></svg>
                            ${p.pidnum_decrypted}
                        </span>
                    `;
                } else {
                    rrnHTML = `<span style="color:var(--text-muted)">Unencrypted / Empty</span>`;
                }

                tr.innerHTML = `
                    <td><strong>#${p.pcode}</strong></td>
                    <td>${p.pname}</td>
                    <td>${birth}</td>
                    <td>${rrnHTML}</td>
                    <td><span class="gender-badge ${genderClass}">${genderText}</span></td>
                    <td>${p.lastcheck || "-"}</td>
                `;
                tbody.appendChild(tr);
            });
        })
        .catch(err => {
            console.error("Search error:", err);
            tbody.innerHTML = `<tr><td colspan="6" class="empty-placeholder" style="color:#f87171;">Error occurred while fetching data. Check server console logs.</td></tr>`;
        });
}

// 4. Select Patient and open details
function selectPatient(pcode) {
    selectedPcode = pcode;
    // Fetch Patient Detail
    fetch(`${API_URL}/api/patients/${pcode}`)
        .then(res => res.json())
        .then(p => {
            selectedPatient = p;
            document.getElementById("detail-name").innerText = p.pname;
            document.getElementById("detail-meta").innerText = `Patient Code: #${p.pcode} | Birth: ${p.pbirth || '-'} (${p.sex === '1' || p.sex === '3' ? 'Male' : 'Female'})`;

            // Render vitals cards & timeline
            renderVitals(p.vitals);

            // Fetch Charts
            fetchCharts(pcode);

            // Fetch Treatment Visits Ledger
            fetchVisits(pcode);

            // Open panel
            document.getElementById("detail-panel").classList.add("open");
            document.getElementById("overlay").classList.add("active");
        })
        .catch(err => {
            console.error("Patient details error:", err);
            alert("Failed to load patient details.");
        });
}

function renderVitals(vitals) {
    const listEl = document.getElementById("vitals-timeline-list");
    listEl.innerHTML = "";

    if (!vitals || vitals.length === 0) {
        // Clear vital widgets
        document.getElementById("vital-weight").innerText = "-";
        document.getElementById("vital-height").innerText = "-";
        document.getElementById("vital-temp").innerText = "-";
        document.getElementById("vital-bp").innerText = "-";
        
        listEl.innerHTML = `<div class="empty-placeholder">No vitals logs found in database.</div>`;
        return;
    }

    // Set current vitals (first index is latest)
    const latest = vitals[0];
    document.getElementById("vital-weight").innerText = latest.weight ? `${latest.weight} kg` : "-";
    document.getElementById("vital-height").innerText = latest.height ? `${latest.height} cm` : "-";
    document.getElementById("vital-temp").innerText = latest.temperatur ? `${latest.temperatur} °C` : "-";
    
    const systolic = latest.systolic || "";
    const diastolic = latest.diastolic || "";
    document.getElementById("vital-bp").innerText = (systolic || diastolic) ? `${systolic}/${diastolic} mmHg` : "-";

    // Render Timeline
    vitals.forEach(v => {
        const timeStr = v.chktime || "";
        const item = document.createElement("div");
        item.className = "timeline-item";
        
        let detailsStr = [];
        if (v.weight) detailsStr.push(`Weight: ${v.weight}kg`);
        if (v.height) detailsStr.push(`Height: ${v.height}cm`);
        if (v.temperatur) detailsStr.push(`Temp: ${v.temperatur}°C`);
        if (v.systolic || v.diastolic) detailsStr.push(`BP: ${v.systolic || '-'}/${v.diastolic || '-'} mmHg`);
        if (v.pulse) detailsStr.push(`Pulse: ${v.pulse} bpm`);
        
        const editData = JSON.stringify(v).replace(/"/g, '&quot;');

        item.innerHTML = `
            <div class="timeline-date">${v.visidate} ${timeStr}</div>
            <div class="timeline-content">
                <div class="timeline-title">Routine Physical Exam</div>
                <div class="timeline-desc">${detailsStr.join("  |  ")}</div>
                <div class="timeline-actions">
                    <button class="btn-small btn-action-edit" onclick="openVitalModal('update', ${editData})">Edit</button>
                    <button class="btn-small btn-action-delete" onclick="deleteVital('${v.visidate}', '${timeStr}')">Delete</button>
                </div>
            </div>
        `;
        listEl.appendChild(item);
    });
}

// Fetch Charts from CHT[YYYY] tables
function fetchCharts(pcode) {
    const chartTimeline = document.getElementById("chart-timeline");
    chartTimeline.innerHTML = `<div class="empty-placeholder">Loading clinical chart notes...</div>`;

    fetch(`${API_URL}/api/charts/${pcode}`)
        .then(res => res.json())
        .then(charts => {
            chartTimeline.innerHTML = "";
            if (charts.length === 0) {
                chartTimeline.innerHTML = `<div class="empty-placeholder">No clinical chart notes found.</div>`;
                return;
            }

            charts.forEach(c => {
                const item = document.createElement("div");
                item.className = "timeline-item";
                
                // Extract diagnoses
                let diagnoses = [];
                for(let i=1; i<=10; i++) {
                    const dx = c[`d${i}`];
                    if(dx && dx.trim()) diagnoses.push(dx.trim());
                }
                
                let dxHTML = "";
                if (diagnoses.length > 0) {
                    dxHTML = `<div class="diagnoses-badges">` + 
                        diagnoses.map(d => `<span class="dx-badge">${d}</span>`).join("") + 
                        `</div>`;
                }

                const symptom = c.symptom || "No symptom text entered.";
                const docText = c.doc ? `Doctor Code: #${c.doc}` : "Unknown Doctor";
                const editData = JSON.stringify(c).replace(/"/g, '&quot;');

                item.innerHTML = `
                    <div class="timeline-date">${c.visidate} ${c.visitime || ''} (${c.source_table})</div>
                    <div class="timeline-content">
                        <div class="timeline-title" style="display:flex; justify-content:space-between;">
                            <span>Clinical Visit Chart Record</span>
                            <span style="font-size:0.8rem; color:var(--accent-secondary); font-weight:normal;">${docText}</span>
                        </div>
                        <div class="timeline-desc">${symptom}</div>
                        ${dxHTML}
                        <div class="timeline-actions">
                            <button class="btn-small btn-action-edit" onclick="openChartModal('update', ${editData})">Edit</button>
                            <button class="btn-small btn-action-delete" onclick="deleteChart('${c.visidate}', '${c.visitime || ''}', '${c.source_table}')">Delete</button>
                        </div>
                    </div>
                `;
                chartTimeline.appendChild(item);
            });
        })
        .catch(err => {
            console.error("Charts error:", err);
            chartTimeline.innerHTML = `<div class="empty-placeholder" style="color:#f87171;">Failed to load charts.</div>`;
        });
}

// Fetch Visits Ledger from MTSMTR database
function fetchVisits(pcode) {
    const ledgerTimeline = document.getElementById("ledger-timeline");
    ledgerTimeline.innerHTML = `<div class="empty-placeholder">Loading billing and visit ledgers...</div>`;

    fetch(`${API_URL}/api/visits/${pcode}`)
        .then(res => res.json())
        .then(visits => {
            ledgerTimeline.innerHTML = "";
            
            // Update header stats
            document.getElementById("stat-total-visits").innerText = visits.length;
            
            let lastFeeVal = "₩0";
            let vaxCount = 0;
            
            if (visits.length === 0) {
                ledgerTimeline.innerHTML = `<div class="empty-placeholder">No ledger records found.</div>`;
                document.getElementById("stat-last-fee").innerText = "₩0";
                document.getElementById("stat-vax-count").innerText = "0";
                return;
            }

            // Find latest fee
            const latestMtr = visits[0];
            if (latestMtr.totalfee) {
                lastFeeVal = `₩${Number(latestMtr.totalfee).toLocaleString()}`;
            }
            document.getElementById("stat-last-fee").innerText = lastFeeVal;

            // Render ledger rows
            visits.forEach(v => {
                const item = document.createElement("div");
                item.className = "timeline-item";
                
                // Count vax
                if (v.vax) vaxCount++;
                if (v.vax2) vaxCount++;

                let feeHTML = "";
                if (v.totalfee !== undefined) {
                    feeHTML = `
                        <div style="margin-top: 0.6rem; border-top: 1px dashed rgba(255,255,255,0.05); padding-top: 0.4rem;">
                            <div class="ledger-fee-row">
                                <span>Patient Co-pay (본인부담금):</span>
                                <span>₩${Number(v.selfee || 0).toLocaleString()}</span>
                            </div>
                            <div class="ledger-fee-row">
                                <span>Insurance Billing (공단청구금):</span>
                                <span>₩${Number(v.genfee || 0).toLocaleString()}</span>
                            </div>
                            <div class="ledger-fee-row">
                                <span>Total Treatment Fee (총진료비):</span>
                                <span>₩${Number(v.totalfee || 0).toLocaleString()}</span>
                            </div>
                        </div>
                    `;
                }

                let treatments = [];
                if (v.vax) treatments.push(`Vaccine: ${v.vax}`);
                if (v.vax2) treatments.push(`Vaccine 2: ${v.vax2}`);
                if (v.inj1) treatments.push(`Inj. Memo: ${v.inj1}`);
                if (v.inj2) treatments.push(`Inj. Memo 2: ${v.inj2}`);

                let treatmentHTML = "";
                if (treatments.length > 0) {
                    treatmentHTML = `
                        <div style="margin-bottom:0.4rem; color:var(--accent-secondary); font-size:0.85rem; font-weight:500;">
                            ${treatments.join("  |  ")}
                        </div>
                    `;
                }

                const vitalsPart = [];
                if (v.weight) vitalsPart.push(`Weight: ${v.weight}kg`);
                if (v.height) vitalsPart.push(`Height: ${v.height}cm`);
                if (v.temperatur) vitalsPart.push(`Temp: ${v.temperatur}°C`);
                
                let vitalsHTML = "";
                if (vitalsPart.length > 0) {
                    vitalsHTML = `<p style="font-size:0.8rem; color:var(--text-muted); margin-bottom:0.25rem;">Vitals checked: ${vitalsPart.join(", ")}</p>`;
                }

                const editData = JSON.stringify(v).replace(/"/g, '&quot;');
                const rowId = v["#"] || 0;

                item.innerHTML = `
                    <div class="timeline-date">${v.visidate} ${v.visitime || ''} (${v.source_table})</div>
                    <div class="timeline-content">
                        <div class="timeline-title" style="display:flex; justify-content:space-between;">
                            <span>Medical Treatment Ledger (MTR)</span>
                            <span style="font-size:0.8rem; color:var(--text-muted);">Age: ${v.age || '-'}</span>
                        </div>
                        ${treatmentHTML}
                        ${vitalsHTML}
                        ${feeHTML}
                        <div class="timeline-actions">
                            <button class="btn-small btn-action-edit" onclick="openLedgerModal('update', ${editData})">Edit</button>
                            <button class="btn-small btn-action-delete" onclick="deleteLedger(${rowId}, '${v.source_table}')">Delete</button>
                        </div>
                    </div>
                `;
                ledgerTimeline.appendChild(item);
            });

            // Update total vax count
            document.getElementById("stat-vax-count").innerText = vaxCount;
        })
        .catch(err => {
            console.error("Visits error:", err);
            ledgerTimeline.innerHTML = `<div class="empty-placeholder" style="color:#f87171;">Failed to load ledger records.</div>`;
        });
}

// Close Detail Slide-over
function closeDetailPanel() {
    document.getElementById("detail-panel").classList.remove("open");
    document.getElementById("overlay").classList.remove("active");
}

// Switch Tabs in Slide-over
function switchTab(tabId) {
    // Headers
    const tabBtns = document.querySelectorAll(".tab-btn");
    tabBtns.forEach(btn => btn.classList.remove("active"));
    
    // Find clicked button
    const activeBtn = Array.from(tabBtns).find(btn => btn.getAttribute("onclick").includes(tabId));
    if (activeBtn) activeBtn.classList.add("active");

    // Contents
    const tabContents = document.querySelectorAll(".tab-content");
    tabContents.forEach(content => content.classList.remove("active"));
    
    document.getElementById(tabId).classList.add("active");
}

// 5. Waitlist CRUD handlers
function submitCheckIn() {
    if (!selectedPcode) {
        alert("Please select a patient first.");
        return;
    }

    const reqData = {
        pcode: selectedPcode,
        roomcode: 1,
        roomnm: "제1진료실",
        deptcode: "14",
        deptnm: "가정의학과",
        doctrcode: "63221",
        doctrnm: "한유석"
    };

    if (selectedPatient) {
        reqData.pname = selectedPatient.pname;
        reqData.pbirth = selectedPatient.pbirth;
    }

    fetch(`${API_URL}/api/waiting`, {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify(reqData)
    })
    .then(res => {
        if (!res.ok) {
            return res.json().then(err => { throw new Error(err.detail || "접수 실패"); });
        }
        return res.json();
    })
    .then(data => {
        fetchWaitlist();
        alert(data.message || "대기 접수되었습니다.");
    })
    .catch(err => {
        console.error("Check-in error:", err);
        alert(`대기 접수 중 오류 발생: ${err.message}`);
    });
}

function deleteFromWaitlist(event, resid1, pname) {
    // Stop click event propagation to prevent selectPatient from running
    if (event) {
        event.stopPropagation();
    }

    if (!confirm(`[${pname}] 환자의 대기 상태를 완료 혹은 취소하시겠습니까?\n진료가 시작되지 않은 경우 ledger 기록도 삭제됩니다.`)) {
        return;
    }

    fetch(`${API_URL}/api/waiting/${resid1}`, {
        method: "DELETE"
    })
    .then(res => {
        if (!res.ok) {
            return res.json().then(err => { throw new Error(err.detail || "삭제 실패"); });
        }
        return res.json();
    })
    .then(data => {
        fetchWaitlist();
        alert(data.message || "대기가 삭제되었습니다.");
    })
    .catch(err => {
        console.error("Delete error:", err);
        alert(`대기 삭제 중 오류 발생: ${err.message}`);
    });
}

// 6. Generic Modal Open/Close helpers
function openModal(modalId) {
    const modal = document.getElementById(modalId);
    modal.style.display = "flex";
    setTimeout(() => {
        modal.classList.add("active");
    }, 10);
}

function closeModal(modalId) {
    const modal = document.getElementById(modalId);
    modal.classList.remove("active");
    setTimeout(() => {
        modal.style.display = "none";
    }, 300);
}

// 7. EMR Vitals Form & CRUD JavaScript Handlers
function openVitalModal(action, data = null) {
    document.getElementById("vital-form-action").value = action;
    const datetimeFields = document.getElementById("vital-datetime-fields");

    if (action === "create") {
        document.getElementById("vital-modal-title").innerText = "Add Vitals History";
        
        const now = new Date();
        const yyyy = now.getFullYear();
        const mm = String(now.getMonth() + 1).padStart(2, '0');
        const dd = String(now.getDate()).padStart(2, '0');
        const hh = String(now.getHours()).padStart(2, '0');
        const min = String(now.getMinutes()).padStart(2, '0');
        const sec = String(now.getSeconds()).padStart(2, '0');
        
        document.getElementById("vital-date-input").value = `${yyyy}-${mm}-${dd}`;
        document.getElementById("vital-time-input").value = `${hh}:${min}:${sec}`;
        datetimeFields.style.display = "grid";

        document.getElementById("vital-weight-input").value = "";
        document.getElementById("vital-height-input").value = "";
        document.getElementById("vital-temp-input").value = "";
        document.getElementById("vital-pulse-input").value = "";
        document.getElementById("vital-systolic-input").value = "";
        document.getElementById("vital-diastolic-input").value = "";
    } else {
        document.getElementById("vital-modal-title").innerText = "Edit Vitals History";
        datetimeFields.style.display = "none";
        
        document.getElementById("vital-form-visidate").value = data.visidate;
        document.getElementById("vital-form-chktime").value = data.chktime;
        document.getElementById("vital-weight-input").value = data.weight || "";
        document.getElementById("vital-height-input").value = data.height || "";
        document.getElementById("vital-temp-input").value = data.temperatur || "";
        document.getElementById("vital-pulse-input").value = data.pulse || "";
        document.getElementById("vital-systolic-input").value = data.systolic || "";
        document.getElementById("vital-diastolic-input").value = data.diastolic || "";
    }
    openModal("vital-modal");
}

function submitVitalForm() {
    const action = document.getElementById("vital-form-action").value;
    const weight = document.getElementById("vital-weight-input").value.trim();
    const height = document.getElementById("vital-height-input").value.trim();
    const temp = document.getElementById("vital-temp-input").value.trim();
    const pulse = document.getElementById("vital-pulse-input").value.trim();
    const systolic = document.getElementById("vital-systolic-input").value.trim();
    const diastolic = document.getElementById("vital-diastolic-input").value.trim();

    let payload = {
        pcode: selectedPcode,
        weight: weight || null,
        height: height || null,
        temperatur: temp || null,
        pulse: pulse || null,
        systolic: systolic || null,
        diastolic: diastolic || null
    };

    let url = `${API_URL}/api/vitals`;
    let method = "POST";

    if (action === "create") {
        payload.visidate = document.getElementById("vital-date-input").value;
        payload.chktime = document.getElementById("vital-time-input").value;
    } else {
        payload.visidate = document.getElementById("vital-form-visidate").value;
        payload.chktime = document.getElementById("vital-form-chktime").value;
        method = "PUT";
    }

    fetch(url, {
        method: method,
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify(payload)
    })
    .then(res => {
        if (!res.ok) {
            return res.json().then(err => { throw new Error(err.detail || "오류 발생"); });
        }
        return res.json();
    })
    .then(data => {
        closeModal("vital-modal");
        selectPatient(selectedPcode);
        alert(data.message || "바이탈이 저장되었습니다.");
    })
    .catch(err => {
        console.error("Vitals submit error:", err);
        alert(`저장 실패: ${err.message}`);
    });
}

function deleteVital(visidate, chktime) {
    if (!confirm(`바이탈 기록 (${visidate} ${chktime})을 완전히 삭제하시겠습니까?`)) {
        return;
    }

    fetch(`${API_URL}/api/vitals?pcode=${selectedPcode}&visidate=${visidate}&chktime=${encodeURIComponent(chktime)}`, {
        method: "DELETE"
    })
    .then(res => {
        if (!res.ok) {
            return res.json().then(err => { throw new Error(err.detail || "삭제 실패"); });
        }
        return res.json();
    })
    .then(data => {
        selectPatient(selectedPcode);
        alert(data.message || "바이탈 기록이 삭제되었습니다.");
    })
    .catch(err => {
        console.error("Vitals delete error:", err);
        alert(`삭제 실패: ${err.message}`);
    });
}

// 8. EMR Chart Notes Form & CRUD JavaScript Handlers
function openChartModal(action, data = null) {
    document.getElementById("chart-form-action").value = action;
    const dateInput = document.getElementById("chart-date-input");
    const timeInput = document.getElementById("chart-time-input");

    if (action === "create") {
        document.getElementById("chart-modal-title").innerText = "Add Clinical Chart Note";
        dateInput.disabled = false;
        timeInput.disabled = false;

        const now = new Date();
        const yyyy = now.getFullYear();
        const mm = String(now.getMonth() + 1).padStart(2, '0');
        const dd = String(now.getDate()).padStart(2, '0');
        const hh = String(now.getHours()).padStart(2, '0');
        const min = String(now.getMinutes()).padStart(2, '0');
        const sec = String(now.getSeconds()).padStart(2, '0');

        dateInput.value = `${yyyy}-${mm}-${dd}`;
        timeInput.value = `${hh}:${min}:${sec}`;

        document.getElementById("chart-symptom-input").value = "";
        document.getElementById("chart-doc-input").value = "63221";
        for (let i = 1; i <= 10; i++) {
            document.getElementById(`chart-d${i}`).value = "";
        }
    } else {
        document.getElementById("chart-modal-title").innerText = "Edit Clinical Chart Note";
        dateInput.disabled = true;
        timeInput.disabled = true;

        document.getElementById("chart-form-visidate").value = data.visidate;
        document.getElementById("chart-form-visitime").value = data.visitime || "";
        document.getElementById("chart-form-source-table").value = data.source_table;

        dateInput.value = data.visidate;
        timeInput.value = data.visitime || "";

        document.getElementById("chart-symptom-input").value = data.symptom || "";
        document.getElementById("chart-doc-input").value = data.doc || "";
        for (let i = 1; i <= 10; i++) {
            document.getElementById(`chart-d${i}`).value = data[`d${i}`] || "";
        }
    }
    openModal("chart-modal");
}

function submitChartForm() {
    const action = document.getElementById("chart-form-action").value;
    const symptom = document.getElementById("chart-symptom-input").value.trim();
    const doc = document.getElementById("chart-doc-input").value.trim();
    
    let payload = {
        pcode: selectedPcode,
        symptom: symptom || null,
        doc: doc || null
    };

    for (let i = 1; i <= 10; i++) {
        const val = document.getElementById(`chart-d${i}`).value.trim();
        payload[`d${i}`] = val || null;
    }

    let url = `${API_URL}/api/charts`;
    let method = "POST";

    if (action === "create") {
        payload.visidate = document.getElementById("chart-date-input").value;
        payload.visitime = document.getElementById("chart-time-input").value;
    } else {
        payload.visidate = document.getElementById("chart-form-visidate").value;
        payload.visitime = document.getElementById("chart-form-visitime").value;
        payload.source_table = document.getElementById("chart-form-source-table").value;
        method = "PUT";
    }

    fetch(url, {
        method: method,
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify(payload)
    })
    .then(res => {
        if (!res.ok) {
            return res.json().then(err => { throw new Error(err.detail || "오류 발생"); });
        }
        return res.json();
    })
    .then(data => {
        closeModal("chart-modal");
        fetchCharts(selectedPcode);
        alert(data.message || "차트 노트가 저장되었습니다.");
    })
    .catch(err => {
        console.error("Charts submit error:", err);
        alert(`저장 실패: ${err.message}`);
    });
}

function deleteChart(visidate, visitime, source_table) {
    if (!confirm(`차트 기록 (${visidate} ${visitime || ''})을 완전히 삭제하시겠습니까?`)) {
        return;
    }

    fetch(`${API_URL}/api/charts?pcode=${selectedPcode}&visidate=${visidate}&visitime=${encodeURIComponent(visitime)}&source_table=${source_table}`, {
        method: "DELETE"
    })
    .then(res => {
        if (!res.ok) {
            return res.json().then(err => { throw new Error(err.detail || "삭제 실패"); });
        }
        return res.json();
    })
    .then(data => {
        fetchCharts(selectedPcode);
        alert(data.message || "차트 기록이 삭제되었습니다.");
    })
    .catch(err => {
        console.error("Charts delete error:", err);
        alert(`삭제 실패: ${err.message}`);
    });
}

// 9. EMR Medical Ledger & Visits Form & CRUD JavaScript Handlers
function openLedgerModal(action, data = null) {
    document.getElementById("ledger-form-action").value = action;
    const dateInput = document.getElementById("ledger-date-input");
    const timeInput = document.getElementById("ledger-time-input");

    if (action === "create") {
        document.getElementById("ledger-modal-title").innerText = "Add Visit Ledger Record";
        dateInput.disabled = false;
        timeInput.disabled = false;

        const now = new Date();
        const yyyy = now.getFullYear();
        const mm = String(now.getMonth() + 1).padStart(2, '0');
        const dd = String(now.getDate()).padStart(2, '0');
        const hh = String(now.getHours()).padStart(2, '0');
        const min = String(now.getMinutes()).padStart(2, '0');
        const sec = String(now.getSeconds()).padStart(2, '0');

        dateInput.value = `${yyyy}-${mm}-${dd}`;
        timeInput.value = `${hh}:${min}:${sec}`;

        document.getElementById("ledger-weight").value = "";
        document.getElementById("ledger-height").value = "";
        document.getElementById("ledger-temp").value = "";
        document.getElementById("ledger-pulse").value = "";
        document.getElementById("ledger-systolic").value = "";
        document.getElementById("ledger-diastolic").value = "";

        document.getElementById("ledger-vax").value = "";
        document.getElementById("ledger-vax2").value = "";
        document.getElementById("ledger-inj1").value = "";
        document.getElementById("ledger-inj2").value = "";

        document.getElementById("ledger-selfee").value = 0;
        document.getElementById("ledger-genfee").value = 0;
        document.getElementById("ledger-totalfee").value = 0;

        document.getElementById("ledger-doc").value = "63221";
        document.getElementById("ledger-fin").value = "";
    } else {
        document.getElementById("ledger-modal-title").innerText = "Edit Visit Ledger Record";
        dateInput.disabled = true;
        timeInput.disabled = true;

        document.getElementById("ledger-form-id").value = data["#"];
        document.getElementById("ledger-form-source-table").value = data.source_table;

        dateInput.value = data.visidate;
        timeInput.value = data.visitime || "";

        document.getElementById("ledger-weight").value = data.weight || "";
        document.getElementById("ledger-height").value = data.height || "";
        document.getElementById("ledger-temp").value = data.temperatur || "";
        document.getElementById("ledger-pulse").value = data.pulse || "";
        document.getElementById("ledger-systolic").value = data.systolic || "";
        document.getElementById("ledger-diastolic").value = data.diastolic || "";

        document.getElementById("ledger-vax").value = data.vax || "";
        document.getElementById("ledger-vax2").value = data.vax2 || "";
        document.getElementById("ledger-inj1").value = data.inj1 || "";
        document.getElementById("ledger-inj2").value = data.inj2 || "";

        document.getElementById("ledger-selfee").value = data.selfee || 0;
        document.getElementById("ledger-genfee").value = data.genfee || 0;
        document.getElementById("ledger-totalfee").value = data.totalfee || 0;

        document.getElementById("ledger-doc").value = data.doc || "";
        document.getElementById("ledger-fin").value = data.fin || "";
    }
    openModal("ledger-modal");
}

function submitLedgerForm() {
    const action = document.getElementById("ledger-form-action").value;
    const weight = document.getElementById("ledger-weight").value.trim();
    const height = document.getElementById("ledger-height").value.trim();
    const temp = document.getElementById("ledger-temp").value.trim();
    const pulse = document.getElementById("ledger-pulse").value.trim();
    const systolic = document.getElementById("ledger-systolic").value.trim();
    const diastolic = document.getElementById("ledger-diastolic").value.trim();

    const vax = document.getElementById("ledger-vax").value.trim();
    const vax2 = document.getElementById("ledger-vax2").value.trim();
    const inj1 = document.getElementById("ledger-inj1").value.trim();
    const inj2 = document.getElementById("ledger-inj2").value.trim();

    const selfee = parseInt(document.getElementById("ledger-selfee").value) || 0;
    const genfee = parseInt(document.getElementById("ledger-genfee").value) || 0;
    const totalfee = parseInt(document.getElementById("ledger-totalfee").value) || 0;

    const doc = document.getElementById("ledger-doc").value.trim();
    const fin = document.getElementById("ledger-fin").value.trim();

    let payload = {
        pcode: selectedPcode,
        weight: weight || null,
        height: height || null,
        temperatur: temp || null,
        pulse: pulse || null,
        systolic: systolic || null,
        diastolic: diastolic || null,
        vax: vax || null,
        vax2: vax2 || null,
        inj1: inj1 || null,
        inj2: inj2 || null,
        selfee: selfee,
        genfee: genfee,
        totalfee: totalfee,
        doc: doc || null,
        fin: fin || null
    };

    let url = `${API_URL}/api/visits`;
    let method = "POST";

    if (action === "create") {
        payload.visidate = document.getElementById("ledger-date-input").value;
        payload.visitime = document.getElementById("ledger-time-input").value;
    } else {
        payload.id = parseInt(document.getElementById("ledger-form-id").value);
        payload.source_table = document.getElementById("ledger-form-source-table").value;
        method = "PUT";
    }

    fetch(url, {
        method: method,
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify(payload)
    })
    .then(res => {
        if (!res.ok) {
            return res.json().then(err => { throw new Error(err.detail || "오류 발생"); });
        }
        return res.json();
    })
    .then(data => {
        closeModal("ledger-modal");
        fetchVisits(selectedPcode);
        alert(data.message || "진료 기록 대장이 저장되었습니다.");
    })
    .catch(err => {
        console.error("Ledger submit error:", err);
        alert(`저장 실패: ${err.message}`);
    });
}

function deleteLedger(id, source_table) {
    if (!confirm(`진료기록 대장 record (ID: ${id} in ${source_table})를 완전히 삭제하시겠습니까?`)) {
        return;
    }

    fetch(`${API_URL}/api/visits?id=${id}&source_table=${source_table}`, {
        method: "DELETE"
    })
    .then(res => {
        if (!res.ok) {
            return res.json().then(err => { throw new Error(err.detail || "삭제 실패"); });
        }
        return res.json();
    })
    .then(data => {
        fetchVisits(selectedPcode);
        alert(data.message || "진료기록 대장이 삭제되었습니다.");
    })
    .catch(err => {
        console.error("Ledger delete error:", err);
        alert(`삭제 실패: ${err.message}`);
    });
}
