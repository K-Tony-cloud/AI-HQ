import { useModal } from '../../context/ModalContext'
import { EditEventModal } from '../admin/EditEventModal'
import { AddEventModal } from '../admin/AddEventModal'
import { CreateOperationModal } from '../admin/CreateOperationModal'
import { ImportOperationModal } from '../admin/ImportOperationModal'
import { AuditPanel } from '../admin/AuditPanel'
import { PinLoginModal } from '../admin/PinLoginModal'

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
      return (
        <PinLoginModal
          onSuccess={() => { props.onSuccess?.(); closeModal() }}
          onClose={closeModal}
        />
      )

    default:
      return null
  }
}
