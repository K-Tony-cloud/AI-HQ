/**
 * @typedef {'briefing'|'security'|'movement'|'ceremony'|'logistics'|'emergency'} EventType
 * @typedef {'upcoming'|'active'|'completed'|'resolved'} EventStatus
 * @typedef {'normal'|'high'|'critical'} EventPriority
 * @typedef {'active'|'upcoming-near'|'upcoming'|'past'} EventState
 * @typedef {'alert'|'update'|'resolved'|'info'|'completed'} LogType
 */

/**
 * @typedef {Object} OperationEvent
 * @property {string}        id
 * @property {string}        date
 * @property {string}        planned_time
 * @property {string|null}   actual_time
 * @property {string|null}   end_time
 * @property {string}        title
 * @property {EventStatus}   status
 * @property {EventType}     type
 * @property {string}        detail
 * @property {string}        reporter
 * @property {string}        location
 * @property {number}        duration
 * @property {EventPriority} priority
 */

/**
 * @typedef {Object} OperationMeta
 * @property {string} id
 * @property {string} name
 * @property {string} date
 * @property {string} classification
 * @property {string} commander
 * @property {string} startTime
 * @property {string} endTime
 * @property {string} venue
 * @property {string} status
 */

/**
 * @typedef {Object} EventLog
 * @property {string}  id
 * @property {string}  event_id
 * @property {string}  time
 * @property {string}  message
 * @property {string}  user
 * @property {LogType} type
 */
