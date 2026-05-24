/**
 * SeedData.gs — populate the Spreadsheet with operations + events + logs
 *
 * Run seedAll() once after initSchema() to get a working dataset.
 */

function seedAll() {
  clearSheetData(SHEET_NAMES.OPERATIONS)
  clearSheetData(SHEET_NAMES.EVENTS)
  clearSheetData(SHEET_NAMES.LOGS)
  seedMeta()
  seedOperations()
  SEED_EVENTS.forEach(e => createEvent(e))
  SEED_LOGS.forEach(l => createLog(l))
  Logger.log('Seeded ' + SEED_EVENTS.length + ' events and ' + SEED_LOGS.length + ' logs.')
}

function clearSheetData(sheetName) {
  const sheet = getOrCreateSheet(sheetName)
  const last  = sheet.getLastRow()
  if (last > 1) sheet.deleteRows(2, last - 1)
}

function seedMeta() {
  const sheet = getOrCreateSheet(SHEET_NAMES.META)
  if (sheet.getLastRow() > 1) sheet.deleteRow(2)
  sheet.appendRow([
    'OP-2026-0522', 'Operation Royal Passage', '2026-05-22', 'RESTRICTED',
    'COL. WICHAI SUWAN', '09:00', '20:00', 'Bangkok Metropolitan Area',
    'ACTIVE', new Date().toISOString(),
  ])
}

function seedOperations() {
  const ops = [
    {
      id: 'OP-2026-0522', title: 'Operation Royal Passage', date: '2026-05-22',
      classification: 'RESTRICTED', commander: 'COL. WICHAI SUWAN',
      start_time: '09:00', end_time: '20:00', venue: 'Bangkok Metropolitan Area',
      status: 'ACTIVE',
    },
    {
      id: 'OP-2026-0524', title: 'Operation Northern Survey', date: '2026-05-24',
      classification: 'CONFIDENTIAL', commander: 'COL. WICHAI SUWAN',
      start_time: '08:00', end_time: '18:00', venue: 'Chiang Mai Province',
      status: 'ACTIVE',
    },
  ]
  const now = new Date().toISOString()
  ops.forEach(op => {
    appendRow(SHEET_NAMES.OPERATIONS, { ...op, created_at: now, updated_at: now })
  })
}

const SEED_EVENTS = [
  { id:'EVT-001', operation_id:'OP-2026-0522', date:'2026-05-22', planned_time:'09:00', actual_time:'09:02', end_time:'09:25', title:'Morning Operations Briefing',                 status:'completed', type:'briefing',  reporter:'MAJ. PRASONG',   location:'Command Center Alpha',                    duration:25,  priority:'high'     },
  { id:'EVT-002', operation_id:'OP-2026-0522', date:'2026-05-22', planned_time:'09:30', actual_time:'09:28', end_time:'09:55', title:'Security Sweep — Zone Alpha',                  status:'completed', type:'security',  reporter:'CPT. NATTAPOL',  location:'Grand Palace Hotel',                      duration:25,  priority:'critical' },
  { id:'EVT-003', operation_id:'OP-2026-0522', date:'2026-05-22', planned_time:'10:00', actual_time:'10:05', end_time:'10:28', title:'Convoy Assembly — Formation A',                 status:'completed', type:'movement',  reporter:'CPT. KITTISAK',  location:'Staging Area — Hotel Basement',            duration:28,  priority:'high'     },
  { id:'EVT-004', operation_id:'OP-2026-0522', date:'2026-05-22', planned_time:'10:30', actual_time:'10:33', end_time:'10:45', title:'VIP Departure — Hotel to Route Alpha',           status:'completed', type:'movement',  reporter:'SGT. WISIT',     location:'Grand Palace Hotel → Route Alpha',         duration:12,  priority:'critical' },
  { id:'EVT-005', operation_id:'OP-2026-0522', date:'2026-05-22', planned_time:'10:45', actual_time:'10:44', end_time:'10:52', title:'Route Alpha — All Clear Confirmed',             status:'completed', type:'security',  reporter:'LT. APICHAT',    location:'Route Alpha Corridor',                    duration:8,   priority:'high'     },
  { id:'EVT-006', operation_id:'OP-2026-0522', date:'2026-05-22', planned_time:'11:00', actual_time:'11:07', end_time:'11:55', title:'Arrival — Government House Venue',              status:'completed', type:'ceremony',  reporter:'MAJ. PRASONG',   location:'Government House, Bangkok',               duration:48,  priority:'critical' },
  { id:'EVT-007', operation_id:'OP-2026-0522', date:'2026-05-22', planned_time:'11:00', actual_time:'11:05', end_time:'12:30', title:'Formal Inspection Ceremony',                   status:'completed', type:'ceremony',  reporter:'COL. WICHAI',    location:'Government House — Main Courtyard',       duration:85,  priority:'critical' },
  { id:'EVT-008', operation_id:'OP-2026-0522', date:'2026-05-22', planned_time:'12:30', actual_time:'12:38', end_time:'13:00', title:'Luncheon — VIP Holding',                       status:'completed', type:'logistics', reporter:'CPT. NATTAPOL',  location:'Government House — State Dining Room',   duration:22,  priority:'normal'   },
  { id:'EVT-009', operation_id:'OP-2026-0522', date:'2026-05-22', planned_time:'13:00', actual_time:'13:02', end_time:'13:45', title:'Private Bilateral Meeting',                    status:'completed', type:'briefing',  reporter:'MAJ. PRASONG',   location:'Government House — Cabinet Room',         duration:43,  priority:'critical' },
  { id:'EVT-010', operation_id:'OP-2026-0522', date:'2026-05-22', planned_time:'14:00', actual_time:'13:58', end_time:'14:15', title:'🚨 EMERGENCY: Traffic Obstruction — Route Bravo', status:'resolved',  type:'emergency', reporter:'SGT. PRATEEP',   location:'Ratchadamnoen Avenue — Intersection 4', duration:17,  priority:'critical' },
  { id:'EVT-011', operation_id:'OP-2026-0522', date:'2026-05-22', planned_time:'14:00', actual_time:'14:16', end_time:'14:35', title:'Route Bravo Alternate — Activated',              status:'completed', type:'logistics', reporter:'CPT. KITTISAK',  location:'Charoen Krung Road Corridor',             duration:19,  priority:'high'     },
  { id:'EVT-012', operation_id:'OP-2026-0522', date:'2026-05-22', planned_time:'14:30', actual_time:'14:38', end_time:'15:05', title:'Transit — Government House to Cultural Center', status:'completed', type:'movement',  reporter:'SGT. WISIT',     location:'Route Bravo Alternate',                   duration:27,  priority:'high'     },
  { id:'EVT-013', operation_id:'OP-2026-0522', date:'2026-05-22', planned_time:'15:00', actual_time:'15:08', end_time:'16:00', title:'Cultural Heritage Exhibition — VIP Tour',        status:'active',    type:'ceremony',  reporter:'LT. APICHAT',    location:'National Cultural Center — Grand Hall',   duration:52,  priority:'high'     },
  { id:'EVT-014', operation_id:'OP-2026-0522', date:'2026-05-22', planned_time:'16:00', actual_time:'',      end_time:'',      title:'Departure — Cultural Center',                  status:'upcoming',  type:'movement',  reporter:'CPT. NATTAPOL',  location:'National Cultural Center — South Exit',   duration:15,  priority:'high'     },
  { id:'EVT-015', operation_id:'OP-2026-0522', date:'2026-05-22', planned_time:'16:15', actual_time:'',      end_time:'',      title:'Press Center — Security Sweep',                status:'upcoming',  type:'security',  reporter:'CPT. KITTISAK',  location:'Royal Press Center — Ballroom A',         duration:20,  priority:'high'     },
  { id:'EVT-016', operation_id:'OP-2026-0522', date:'2026-05-22', planned_time:'16:30', actual_time:'',      end_time:'',      title:'Press Conference — Joint Statement',            status:'upcoming',  type:'ceremony',  reporter:'MAJ. PRASONG',   location:'Royal Press Center — Ballroom A',         duration:30,  priority:'critical' },
  { id:'EVT-017', operation_id:'OP-2026-0522', date:'2026-05-22', planned_time:'17:30', actual_time:'',      end_time:'',      title:'Delegate Meeting — Group Alpha',                status:'upcoming',  type:'briefing',  reporter:'COL. WICHAI',    location:'Royal Press Center — Suite 12',           duration:45,  priority:'critical' },
  { id:'EVT-018', operation_id:'OP-2026-0522', date:'2026-05-22', planned_time:'18:00', actual_time:'',      end_time:'',      title:'Evening Security Briefing',                    status:'upcoming',  type:'briefing',  reporter:'CPT. NATTAPOL',  location:'Command Vehicle — Secure Channel',        duration:20,  priority:'normal'   },
  { id:'EVT-019', operation_id:'OP-2026-0522', date:'2026-05-22', planned_time:'18:30', actual_time:'',      end_time:'',      title:'Convoy Assembly — Formation Delta',             status:'upcoming',  type:'movement',  reporter:'CPT. KITTISAK',  location:'Royal Press Center — Secure Parking',     duration:15,  priority:'high'     },
  { id:'EVT-020', operation_id:'OP-2026-0522', date:'2026-05-22', planned_time:'19:00', actual_time:'',      end_time:'',      title:'Gala Dinner — VIP Arrival',                    status:'upcoming',  type:'ceremony',  reporter:'COL. WICHAI',    location:'Grand Hyatt Erawan — Crystal Ballroom',  duration:30,  priority:'critical' },
  { id:'EVT-021', operation_id:'OP-2026-0522', date:'2026-05-22', planned_time:'19:30', actual_time:'',      end_time:'',      title:'State Dinner — Formal Ceremony',               status:'upcoming',  type:'ceremony',  reporter:'MAJ. PRASONG',   location:'Grand Hyatt Erawan — Crystal Ballroom',  duration:150, priority:'critical' },
  { id:'EVT-022', operation_id:'OP-2026-0522', date:'2026-05-22', planned_time:'20:00', actual_time:'',      end_time:'',      title:'Operation Stand Down — Phase 1',               status:'upcoming',  type:'logistics', reporter:'COL. WICHAI',    location:'Command Center Alpha',                    duration:30,  priority:'normal'   },
  { id:'EVT-101', operation_id:'OP-2026-0524', date:'2026-05-24', planned_time:'08:00', actual_time:'',      end_time:'',      title:'Advance Team Deployment — Chiang Mai Airport', status:'upcoming',  type:'security',  reporter:'CPT. NATTAPOL',  location:'Chiang Mai International Airport',        duration:60,  priority:'high'     },
  { id:'EVT-102', operation_id:'OP-2026-0524', date:'2026-05-24', planned_time:'10:00', actual_time:'',      end_time:'',      title:'Site Survey — Northern Command Post',           status:'upcoming',  type:'briefing',  reporter:'MAJ. PRASONG',   location:'Northern Regional Command Post',           duration:90,  priority:'normal'   },
]

const SEED_LOGS = [
  { id:'LOG-001', event_id:'EVT-010', time:'13:58', message:'Traffic incident reported at Ratchadamnoen Intersection 4. Vehicle breakdown blocking 2 lanes.', user:'SGT. PRATEEP',  type:'alert'    },
  { id:'LOG-002', event_id:'EVT-010', time:'14:00', message:'Traffic police unit dispatched to scene. ETA 3 minutes.',                                          user:'CPT. KITTISAK', type:'update'   },
  { id:'LOG-003', event_id:'EVT-010', time:'14:04', message:'Route Bravo declared CLOSED. Alternate route assessment initiated.',                               user:'CPT. NATTAPOL', type:'alert'    },
  { id:'LOG-004', event_id:'EVT-010', time:'14:12', message:'Vehicle removed from obstruction. Road clearance in progress.',                                    user:'SGT. PRATEEP',  type:'update'   },
  { id:'LOG-005', event_id:'EVT-010', time:'14:15', message:'Route Bravo obstruction cleared. Incident resolved. Alternate route remains active.',              user:'CPT. KITTISAK', type:'resolved' },
  { id:'LOG-006', event_id:'EVT-013', time:'15:08', message:'VIP principal arrived at Cultural Center. All 47 exhibition personnel in position.',               user:'LT. APICHAT',   type:'update'   },
  { id:'LOG-007', event_id:'EVT-013', time:'15:22', message:'Tour progressing normally. Currently in Heritage Gallery — Room 4.',                               user:'LT. APICHAT',   type:'update'   },
  { id:'LOG-008', event_id:'EVT-013', time:'15:38', message:'Unscheduled 5-minute extension requested by VIP principal for Textile Gallery.',                   user:'MAJ. PRASONG',  type:'info'     },
  { id:'LOG-009', event_id:'EVT-013', time:'15:45', message:'Currently in Silk Gallery — Room 9. 3 more rooms remaining. Estimated completion 16:05.',          user:'LT. APICHAT',   type:'update'   },
  { id:'LOG-010', event_id:'EVT-007', time:'11:05', message:'Ceremony commenced. Honor guard of 24 in position.',                                               user:'COL. WICHAI',   type:'update'   },
  { id:'LOG-011', event_id:'EVT-007', time:'11:45', message:'Formal address completed. Photography session approved for 10 minutes.',                           user:'MAJ. PRASONG',  type:'update'   },
  { id:'LOG-012', event_id:'EVT-007', time:'12:28', message:'Ceremony concluded successfully. All protocol requirements met. Moving to dining phase.',           user:'COL. WICHAI',   type:'completed'},
  { id:'LOG-013', event_id:'EVT-016', time:'16:15', message:'Press credentials check completed. 43 of 45 accredited media present.',                            user:'CPT. KITTISAK', type:'info'     },
  { id:'LOG-014', event_id:'EVT-016', time:'16:25', message:'Venue ready. Technical setup confirmed. Podium area secured.',                                     user:'SGT. WISIT',    type:'update'   },
]
