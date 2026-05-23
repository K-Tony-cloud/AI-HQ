import { createContext, useContext, useState, useCallback } from 'react'

const FilterContext = createContext(null)

export const FilterProvider = ({ children }) => {
  const [searchQuery,    setSearchQuery]    = useState('')
  const [typeFilter,     setTypeFilter]     = useState('')
  const [statusFilter,   setStatusFilter]   = useState('')
  const [priorityFilter, setPriorityFilter] = useState('')

  const hasActiveFilters =
    searchQuery !== '' || typeFilter !== '' || statusFilter !== '' || priorityFilter !== ''

  const clearFilters = useCallback(() => {
    setSearchQuery('')
    setTypeFilter('')
    setStatusFilter('')
    setPriorityFilter('')
  }, [])

  return (
    <FilterContext.Provider value={{
      searchQuery,    setSearchQuery,
      typeFilter,     setTypeFilter,
      statusFilter,   setStatusFilter,
      priorityFilter, setPriorityFilter,
      clearFilters,
      hasActiveFilters,
    }}>
      {children}
    </FilterContext.Provider>
  )
}

export const useFilter = () => {
  const ctx = useContext(FilterContext)
  if (!ctx) throw new Error('useFilter must be used within FilterProvider')
  return ctx
}
