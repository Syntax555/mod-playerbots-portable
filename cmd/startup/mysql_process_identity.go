package main

const maxMySQLParentDepth = 32

type mysqlProcessIdentity struct {
	parent         uint32
	created        uint64
	sameExecutable bool
}

// Parent PIDs alone are not identities: Windows can reuse an exited parent's
// number while its child still reports that old number. A real ancestor must
// have been created no later than its child. Native callers keep handles open
// while collecting these identities. The current parent snapshot is taken only
// after all handles are held, so stale snapshot links cannot be attached to a PID
// that was reused before its handle was opened.
func validMySQLProcessChain(root, listener uint32, identities map[uint32]mysqlProcessIdentity, currentParents map[uint32]uint32) bool {
	rootIdentity, exists := identities[root]
	if root == 0 || listener == 0 || !exists || !rootIdentity.sameExecutable || rootIdentity.created == 0 {
		return false
	}
	seen := make(map[uint32]bool)
	for pid, depth := listener, 0; depth < maxMySQLParentDepth; depth++ {
		identity, exists := identities[pid]
		if !exists || seen[pid] || !identity.sameExecutable || identity.created == 0 {
			return false
		}
		if pid == root {
			return true
		}
		currentParent, exists := currentParents[pid]
		if !exists || currentParent != identity.parent {
			return false
		}
		seen[pid] = true
		parent, exists := identities[identity.parent]
		if !exists || parent.created > identity.created {
			return false
		}
		pid = identity.parent
	}
	return false
}
