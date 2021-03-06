import collections
import rig.netlist
from six import iteritems, itervalues

from nengo_spinnaker.utils.keyspaces import is_nengo_keyspace


def get_nets_for_placement(nets):
    """Convert a list of N:M nets into a list of Rig nets suitable for
    performing placement.

    Parameters
    ----------
    nets : [:py:class:`~nengo_spinnaker.netlist.NMNet`, ...]
        Iterable of N:M nets to convert

    Yields
    ------
    :py:class:`~rig.netlist.Net`
        1:M net suitable for use with Rig for placement purposes.
    """
    # For each source in each net create a new Rig net
    for net in nets:
        for source in net.sources:
            yield rig.netlist.Net(source, net.sinks, net.weight)


def get_nets_for_routing(resources, nets, placements, allocations):
    """Convert a list of N:M nets into a list of Rig nets suitable for
    performing routing.

    Parameters
    ----------
    resources : {vertex: {resource: requirement}, ...}
    nets : {Signal: :py:class:`~nengo_spinnaker.netlist.NMNet`, ...}
    placements : {vertex: (x, y), ...}
    allocations : {vertex: {resource: :py:class:`slice`}, ...}

    Returns
    -------
    [:py:class:`~rig.netlist.Net`, ...]
        1:M net suitable for use with Rig for routing purposes.
    {vertex: {resource: requirement}, ...}
        An extended copy of the resources dictionary which must be used when
        performing routing with the returned nets.
    {vertex: (x, y), ...}
        An extended copy of the placements dictionary which must be used when
        performing routing with the returned nets.
    {vertex: {resource: :py:class:`slice`}, ...}
        An extended copy of the allocations dictionary which must be used when
        performing routing with the returned nets.
    {:py:class:`~nengo_spinnaker.netlist.NMNet`:
            {(x, y): :py:class:`~rig.netlist.Net`, ...}, ...}
        Map from original nets to co-ordinates and the derived nets which
        originate from them.
    """
    routing_nets = list()  # Nets with which to perform routing
    extended_resources = dict(resources)  # New requirements will be added
    extended_placements = dict(placements)  # New placements will be added
    extended_allocations = dict(allocations)  # New allocations will be added
    derived_nets = collections.defaultdict(dict)  # {Net: {placement: rig.Net}}

    # For each Net build a set of all the co-ordinates from which the net now
    # originates.
    for net in itervalues(nets):
        start_placements = set(placements[v] for v in net.sources)

        # For each of these co-ordinates create a new Rig Net with a new source
        # vertex placed at the given co-ordinate.
        for placement in start_placements:
            # Create a new source vertex and place it at the given placement
            vertex = object()
            extended_placements[vertex] = placement
            extended_resources[vertex] = dict()
            extended_allocations[vertex] = dict()

            # Create a new Rig Net using the new start vertex; add the new Net
            # to the dictionary of derived nets and the list of nets with which
            # to perform routing.
            new_net = rig.netlist.Net(vertex, net.sinks, net.weight)
            routing_nets.append(new_net)
            derived_nets[net][placement] = new_net

    return (routing_nets, extended_resources, extended_placements,
            extended_allocations, derived_nets)


def get_net_keyspaces(placements, nets, derived_nets):
    """Get a map from the nets used during routing to the keyspaces (NOT the
    keys and masks) that should be used when building routing tables.

    Cluster IDs will be applied to any nets which used the default Nengo
    keyspace.

    Parameters
    ----------
    placements : {vertex: (x, y), ...}
    nets : {Signal: NMNet, ...}
        Map from Signals to the multisource nets which implement them.
    derived_nets : {:py:class:`~nengo_spinnaker.netlist.NMNet`:
                    {(x, y): :py:class:`~rig.netlist.Net`, ...}, ...}
        Map from original nets to co-ordinates and the derived nets which
        originate from them as, returned by :py:func:`~.get_routing_nets`.

    Returns
    -------
    {net: keyspace, ...}
        A map from nets to :py:class:`~rig.bitfield.BitField`s that can later
        be used to generate routing tables.
    """
    net_keyspaces = dict()  # Map from derived nets to keyspaces

    for signal, original_net in iteritems(nets):
        ks = signal.keyspace

        for placement, net in iteritems(derived_nets[original_net]):
            # If the keyspace is the default Nengo keyspace then add a cluster
            # ID, otherwise just store the keyspace as is.
            if is_nengo_keyspace(ks):
                # Get all the cluster IDs assigned to vertices with the given
                # placement (there should only be one cluster ID, if there are
                # more it would imply that multiple Nengo objects ended up in
                # the sources for a given Net and it is an error from which we
                # cannot recover).
                cluster_ids = set(vx.cluster for vx in original_net.sources
                                  if placements[vx] == placement)
                assert len(cluster_ids) == 1, "Inconsistent cluster IDs"
                cluster_id = next(iter(cluster_ids)) or 0  # Get the ID

                # Store the keyspace with the cluster ID attached
                net_keyspaces[net] = ks(cluster=cluster_id)
            else:
                # Store the keyspace as is
                net_keyspaces[net] = ks

    return net_keyspaces
