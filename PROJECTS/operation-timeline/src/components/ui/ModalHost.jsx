import { useModal } from '../../context/ModalContext'
import { EditEventModal } from '../admin/EditEventModal'
import { AddEventModal } from '../admin/AddEventModal'
import { CreateOperationModal } from '../admin/CreateOperationModal'
import { ImportOperationModal } from '../admin/ImportOperationModal'
import { AuditPanel } from '../admin/AuditPanel'
import { GoogleLoginModal } from '../admin/GoogleLoginModal'
import { DeletedEventsPanel } from '../admin/DeletedEventsPanel'
import { UserManagementModal } from '../admin/UserManagementModal'
import { ConfirmDeleteModal } from './ConfirmDeleteModal'

export const ModalHost = () => {
  const { activeModal, closeModal } = useModal()
  if (!activeModal) return null

  const { type, props } = activeModal

  switch (type) {
    case 'editEvent':
      return <EditEventModal event={props.event} onClose={closeModal} />

    case 'addEvent':
      return <AddEventModal onClose={closeModal} />

    case 'createOperation':
      return <CreateOperationModal cloneSourceId={props.cloneSourceId || null} onClose={closeModal} />

    case 'importOperation':
      return <ImportOperationModal onClose={closeModal} />

    case 'audit':
      return <AuditPanel onClose={closeModal} />

    case 'pinLogin':
      return <GoogleLoginModal onClose={closeModal} />

    case 'confirmDelete':
      return (
        <ConfirmDeleteModal
          eventTitle={props.eventTitle}
          eventId={props.eventId}
          onConfirm={props.onConfirm}
          onClose={closeModal}
        />
      )

    case 'deletedEvents':
      return <DeletedEventsPanel onClose={closeModal} />

    case 'userManagement':
      return <UserManagementModal onClose={closeModal} />

    default:
      return null
  }
}
