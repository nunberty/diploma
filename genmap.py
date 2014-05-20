'''
    Genetic Linkage Mapper
    Sergey Sysoev, 2013


'''
import sys
import itertools
import collections

OrganismRecord = collections.namedtuple("OrganismRecord",
    ["id", "parent1", "parent2", "sex", "allels"])

class Pedigree(object):
    class Organism(object):
        def __init__(self, record):
            self.id = record.id
            self.sex = record.sex
            self.allels = record.allels
            self.parents = []
            self.children = []

        def is_homozigota_at(self, i):
            return self.allels[2 * i] == self.allels[2 * i + 1]

        def __eq__(self, other):
            return isinstance(other, Pedigree.Organism) and self.id == other.id

        def __hash__(self):
            return hash(self.id)

    def __init__(self, M, number_of_species, locs_names, records):
        self.M = M
        self.number_of_species = number_of_species
        self.locs_names = locs_names
        organism_by_id = {r.id: Pedigree.Organism(r) for r in records}
        for r in records:
            child = organism_by_id[r.id]
            parents = [organism_by_id[p_id] for p_id in [r.parent1, r.parent2] if p_id]
            child.parents = parents
            for p in parents:
                p.children.append(child)
        self.organisms = organism_by_id.values()
        self.reveal_gametes()

    def reveal_gametes(self):
        def store_gamets(organism, g1, g2):
            organism.gamets1 = g1
            organism.gamets2 = g2

        # cycle through all species
        for s in self.organisms:
            # init gametes for the specie
            g1 = range(self.M + 1)
            g2 = range(self.M + 1)
            for i in range(self.M):
                if s.is_homozigota_at(i):
                    g1[i] = g2[i] = s.allels[2 * i]
                else:
                    g1[i] = g2[i] = 0
                g1[self.M] = g2[self.M] = 0                       # we don't know the parent for the gamete yet

            if not s.parents:
                store_gamets(s, g1, g2)
                continue

            # cycle through all loci
            p = s.parents[0]
            for i in range(self.M):
                if g1[i] != 0:                  # we already know this locus
                    continue
                if p.is_homozigota_at(i) and p.allels[2 * i] != 0: # parent is homozygota, but current specie is not
                    g1[i] = p.allels[2 * i]
                    g1[self.M] = p.id                # the parent for the gamete
                    g2[i] = 3 - p.allels[2 * i]     # 2->1, 1->2
                    if len(s.parents) == 2:
                        g2[self.M] = s.parents[1].id   # the parent for the gamete
                    continue
                else:
                    if len(s.parents) == 2:       # look at the other parent
                        m = s.parents[1]
                        if m.is_homozigota_at(i) and m.allels[2 * i] != 0:
                            g2[i] = m.allels[2 * i]
                            g2[self.M] = m.id
                            g1[i] = 3 - m.allels[2 * i]
                            g1[self.M] = p.id

            #
            #  31.05.13  Sysoev. It is useful to assign equal gametes to the parents, because homozygota child of
            #  heterozygota parent can be useful for further data retrival
            #
            if g1[self.M] == 0:
                g1[self.M] = s.parents[0].id
            if g2[self.M] == 0 and len(s.parents) == 2:
                g2[self.M] = s.parents[1].id

            store_gamets(s, g1, g2)

    def process_gametes(self, stat=True):
        # init the CIS - TRANS estimation matrix
        cistrans = []
        for i in range(self.M):
            row = [[0, 0] for _ in range(self.M)]
            cistrans.append(row)

        # cycle through the species
        for s in self.organisms:
            if not s.children:              # no children - no meioses
                continue

            # cycle through all locus combinations
            for i in range(self.M):
                if s.is_homozigota_at(i):
                    continue
                for j in range(i + 1, self.M):
                    if s.is_homozigota_at(j):
                        continue

                    type1 = type2 = rec = nonrec = 0

                    # recycle through the children
                    for ch in s.children:
                        gamete = None
                        if ch.gamets1[self.M] == s.id:    # find our gamete in the child
                            gamete = ch.gamets1
                        if ch.gamets2[self.M] == s.id:
                            gamete = ch.gamets2
                        assert gamete is not None, "cant determine which of gametes is ours. 31.05.13 Sysoev: now this should not happen!"

                        if gamete[i] == 0 or gamete[j] == 0:    # the meiosis was uninformative on these loci
                            continue

                        # gather the statistical info
                        if gamete[i] == gamete[j]:
                            type1 += 1                # AB or ab
                        else:
                            type2 += 1                # Ab or aB

                        # gather the reliable info
                        if ((gamete[i] == s.gamets1[i] and gamete[j] == s.gamets2[j]) or
                                (gamete[i] == s.gamets2[i] and gamete[j] == s.gamets1[j])):
                            rec += 1                # RECOMBINATION
                        else:
                            nonrec += 1             # NO RECOMBINATION

                    if stat and len(s.children) > 4:
                        if rec < min(type1, type2):
                            # print rec, nonrec, type1, type2
                            nonrec = max(type1, type2)
                            rec = min(type1, type2)

                    cistrans[i][j][0] += rec
                    cistrans[i][j][1] += nonrec

        return cistrans

def not_empty_lines(f):
    return itertools.ifilter(lambda x: x,
        itertools.imap(lambda x: x.strip(), f))
#
#    Open and parse the .GEN file
#
def open_file(name):
    with open(name) as f:
        lines = not_empty_lines(f)

        next(lines)                 # number of FAMILIES - not used, assumed 1
        M = int(next(lines))       # number of loci
        locs_names = next(lines).split()  # names of loci

        next(lines)                 # read family number
        number_of_species = int(next(lines))

        records = []               # data array for the whole pedigree
        for _ in range(number_of_species):                  # READ FAMILY
            id, p1, p2, sex = map(int, next(lines).split())     # read species
            allels = [int(a) for a in next(lines).split()]
            records.append(OrganismRecord(id, p1, p2, sex, allels))

        return Pedigree(M, number_of_species, locs_names, records)

#
#    Given the recombination fractions matrix, try to form the order
#
def form_cluster(M, matrix):
    best_cluster = None
    best_cluster_len = 0

    #
    # try to form cluster from every node, than choose best
    #
    for locus in range(M):
        temp = [True] * M
        cluster = []
        temp[locus] = False                # mark as used
        cluster.append(locus)

        # find the first neighbor
        neighbor = None
        dist = 1
        for i in range(M):
            if temp[i] and matrix[locus][i] < dist:
                neighbor = i
                dist = matrix[locus][i]
        if not neighbor:
            if len(cluster) > best_cluster_len:
                best_cluster_len = len(cluster)
                best_cluster = cluster
            continue

        cluster.append(neighbor)
        temp[neighbor] = False

        # find the second neighbor
        neighbor2 = None
        dist = 1
        for i in range(M):
            if temp[i] and matrix[locus][i] < dist:
                neighbor2 = i
                dist = matrix[locus][i]
        if not neighbor2:
            if len(cluster) > best_cluster_len:
                best_cluster_len = len(cluster)
                best_cluster = cluster
            continue
        total_length = matrix[neighbor][neighbor2]

        # build the chain
        while True:
            locus = neighbor
            neighbor = None
            dist = 1
            for i in range(M):
                if temp[i] and matrix[locus][i] < dist and matrix[locus][i] <= total_length:
                    neighbor = i
                    dist = matrix[locus][i]
            if not neighbor:
                if len(cluster) > best_cluster_len:
                    best_cluster_len = len(cluster)
                    best_cluster = cluster
                break

            cluster.append(neighbor)
            temp[neighbor] = False
            #
            # fixing the situation with equal fractions
            #
            for i in range(M):
                if temp[i] and matrix[locus][i] <= dist and matrix[locus][i] <= total_length:
                    cluster.append(i)
                    temp[i] = False
            total_length += dist
    return best_cluster

#
#  We've formed the cluster, but oops.. some loci are not in it. Inserting them...
#
def insert_locus(cluster, locus, matrix):
    # find the closest neighbor
    neighbor1 = None
    dist1 = 1
    for i in range(len(cluster)):
        if matrix[cluster[i]][locus] < dist1:
            dist1 = matrix[cluster[i]][locus]
            neighbor1 = i

    if neighbor1 == 0:                        # near the beginning
        if matrix[locus][cluster[1]] > matrix[cluster[0]][cluster[1]]:
            cluster.insert(0, locus)        # our locus is the first
        else:
            cluster.insert(1, locus)        # no, it is the second
        return cluster
    if neighbor1 == len(cluster) - 1:        # near the end
        if matrix[locus][cluster[neighbor1 - 1]] > matrix[cluster[neighbor1]][cluster[neighbor1 - 1]]:
            cluster.insert(neighbor1 + 1, locus)        # it is last
        else:
            cluster.insert(neighbor1, locus)                # no, before the last
        return cluster

    # it is in the middle. But what is this neighbor? Right or Left?
    if matrix[locus][cluster[neighbor1 - 1]] < matrix[cluster[neighbor1]][cluster[neighbor1 - 1]]:
        cluster.insert(neighbor1, locus)
    else:
        cluster.insert(neighbor1 + 1, locus)
    return cluster

#
#   Given the recombinations, calculate the fractions
#
def process_matrix(M, matrix, number):
    # first of all, calculate the fractions
    fracs = []
    for i in range(M):
        row = []
        for j in range(M):
            if j == i:
                recombinants = 0
                nonrecombinants = 1
            else:
                if j < i + 1:                # initial matrix is triangle (see how we form it). Fracs matrix should be full
                    recombinants = matrix[j][i][0]
                    nonrecombinants = matrix[j][i][1]
                else:
                    recombinants = matrix[i][j][0]
                    nonrecombinants = matrix[i][j][1]

            if recombinants or nonrecombinants:
                row.append(float(recombinants) / (recombinants + nonrecombinants))
            else:
                row.append(2)   # no data for these loci.
                print 'this happened! no data for loci ', i, j
        fracs.append(row)

    return fracs

#
#    process the pedigree. Main function in the module
#         file_name - name of the CHR file with the pedigree data
#         order - order of loci that already known
#         stat - boolean value, whether to use statistical results
#
#    use it like:
#            process_pedigree("c:\\my_file.gen")
#       process_pedigree("c:\\my_file.gen", range(10), False) # first 10 loci are in the right order, use only the reliable results
#
def process_pedigree(file_name, order=None, stat=True):
    order = order or []
    pedigree = open_file(file_name)
    rec = pedigree.process_gametes(stat)
    fracs = process_matrix(pedigree.M, rec, pedigree.number_of_species)

    # get the cluster
    if order:
        cluster = order
    else:
        cluster = form_cluster(pedigree.M, fracs)

    for l in range(pedigree.M):
        if l not in cluster:
            cluster = insert_locus(cluster, l, fracs)


    for i in range(len(cluster)):
        name = pedigree.locs_names[cluster[i]]
        if i < len(cluster) - 1:
            print name, '   ', fracs[cluster[i]][cluster[i + 1]]
        else:
            print name

    return cluster, fracs


# NAME = 'c:\\python27\\Lib\\chr1000.gen'
NAME = 'out2.gen'
if len(sys.argv) > 1:
    NAME = sys.argv[1]


process_pedigree(NAME)
