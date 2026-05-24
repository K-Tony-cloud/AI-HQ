export const MOCK_LOGS = {
  'EVT-010': [
    { id: 'LOG-001', event_id: 'EVT-010', time: '13:58', message: 'Traffic incident reported at Ratchadamnoen Intersection 4. Vehicle breakdown blocking 2 lanes.', user: 'SGT. PRATEEP', type: 'alert' },
    { id: 'LOG-002', event_id: 'EVT-010', time: '14:00', message: 'Traffic police unit dispatched to scene. ETA 3 minutes.', user: 'CPT. KITTISAK', type: 'update' },
    { id: 'LOG-003', event_id: 'EVT-010', time: '14:04', message: 'Route Bravo declared CLOSED. Alternate route assessment initiated.', user: 'CPT. NATTAPOL', type: 'alert' },
    { id: 'LOG-004', event_id: 'EVT-010', time: '14:12', message: 'Vehicle removed from obstruction. Road clearance in progress.', user: 'SGT. PRATEEP', type: 'update' },
    { id: 'LOG-005', event_id: 'EVT-010', time: '14:15', message: 'Route Bravo obstruction cleared. Incident resolved. Alternate route remains active for this operation.', user: 'CPT. KITTISAK', type: 'resolved' },
  ],
  'EVT-013': [
    { id: 'LOG-006', event_id: 'EVT-013', time: '15:08', message: 'VIP principal arrived at Cultural Center. All 47 exhibition personnel in position.', user: 'LT. APICHAT', type: 'update' },
    { id: 'LOG-007', event_id: 'EVT-013', time: '15:22', message: 'Tour progressing normally. Currently in Heritage Gallery — Room 4.', user: 'LT. APICHAT', type: 'update' },
    { id: 'LOG-008', event_id: 'EVT-013', time: '15:38', message: 'Unscheduled 5-minute extension requested by VIP principal for Textile Gallery.', user: 'MAJ. PRASONG', type: 'info' },
    { id: 'LOG-009', event_id: 'EVT-013', time: '15:45', message: 'Currently in Silk Gallery — Room 9. 3 more rooms remaining. Estimated completion 16:05.', user: 'LT. APICHAT', type: 'update' },
  ],
  'EVT-007': [
    { id: 'LOG-010', event_id: 'EVT-007', time: '11:05', message: 'Ceremony commenced. Honor guard of 24 in position.', user: 'COL. WICHAI', type: 'update' },
    { id: 'LOG-011', event_id: 'EVT-007', time: '11:45', message: 'Formal address completed. Photography session approved for 10 minutes.', user: 'MAJ. PRASONG', type: 'update' },
    { id: 'LOG-012', event_id: 'EVT-007', time: '12:28', message: 'Ceremony concluded successfully. All protocol requirements met. Moving to dining phase.', user: 'COL. WICHAI', type: 'completed' },
  ],
  'EVT-016': [
    { id: 'LOG-013', event_id: 'EVT-016', time: '16:15', message: 'Press credentials check completed. 43 of 45 accredited media present.', user: 'CPT. KITTISAK', type: 'info' },
    { id: 'LOG-014', event_id: 'EVT-016', time: '16:25', message: 'Venue ready. Technical setup confirmed. Podium area secured.', user: 'SGT. WISIT', type: 'update' },
  ],
}

export const getLogsForEvent = (eventId) => MOCK_LOGS[eventId] || []
