__author__ = 'yunfanzhang'
import aipy as a, numpy as n, capo
import matplotlib.pyplot as p
import delay_transform as dl_tr, plot_pspec as plotp
import random

#o = optparse.OptionParser()
#a.scripting.add_standard_options(o, chan=True, ant=True, pol=True)
##a.scripting.add_standard_options(o, ant=True, pol=True)
#o.add_option('-t', '--lst', dest='lst', default=-1, help='Choose the time points to include')
#opts,args = o.parse_args(sys.argv[1:])
#print opts, args

c = 299792458.
Mpc2m = 3.086E22 #meters
kB = 1.3806488E-23  #m2 kg s-2 K-1
nu = n.arange(100, 200, 10)*1.E6
nu0 = 150
lamb = c/nu0*1.E6  #m
pref = (2*kB/lamb*lamb)*(2*kB/lamb*lamb)   #(kg s-2 K-1)2
z, Omm, hub = 8.5, 0.27, 0.75
#Y = 17 (((1+z)/10)/(Omm*hub*hub/0.15))^0.5 #Mpc/MHz
#X = 1.9 ((1+z)/10)^0.2/hub                 # Mpc/arcmin
Y = 17*(((1+z)/10)/(Omm/0.15))**0.5 #h Mpc/MHz
X = 1.9*((1+z)/10)**0.2                # h Mpc/arcmin
XSY = 540*((1+z)/10)**0.9  #hub-3 Mpc3 sr-1 Hz-1
B = 10E6   #Hz
W = 0.31  #sr

nchan = 20
nT = 1000
sdf = 100./203  #df in MHz
random.seed()
taulist = n.fft.fftfreq(nchan,sdf)
taulist = n.fft.ifftshift(taulist)
cnt = 0

#test=[]
#for i in range(1000):
#    test.append(random.gauss(0,1))
#p.hist(test,bins=n.arange(-3,3,0.5))
#p.show()

sig = 10
data1, data2, summ = [],[],[]
for n1 in n.arange(nT):
    datnu = []
    for n2 in n.arange(nchan): datnu.append(random.gauss(0,0.5)+random.gauss(0,0.5)*1.j)
    #datnu[len(datnu)/2] = datnu[len(datnu)/2] + sig
    datatau = dl_tr.nu2tau(datnu)

    data1.append(n.array(datatau).transpose())
    #data1.append(n.array(datnu).transpose())
#data1 = n.array(data1).transpose()

p.plot(n.arange(nchan),datnu)
p.title('datnu')
p.show()
p.plot(taulist,datatau)
p.title('datatau')
p.show()

for n1 in n.arange(nT):
    datnu = []
    for n2 in n.arange(nchan):
        datnu.append(random.gauss(0,0.5)+random.gauss(0,0.5)*1.j)
        #datnu.append(1.)
    datnu[len(datnu)/2] = datnu[len(datnu)/2] + sig
    datatau = dl_tr.nu2tau(datnu)
    data2.append(n.array(datatau).transpose())
    #data2.append(n.array(datnu).transpose())
    #print tauchan, datatau[tauchan]

#print "data shapes", data1.shape, data2.shape
print "Average over %d time points" % len(data1)
data1, data2 = n.array(data1),n.array(data2)
print "datashapes", data1.shape, data2.shape
for ind in range(len(taulist)): summ.append(0.)
for ind in range(len(taulist)):
    for ine in range(len(data1)): #loop over nT
        summ[ind] = summ[ind] + n.conjugate(data1[ine][ind])*data1[ine][ind]

result = {}
P=[]
for ind in n.arange(len(summ)):
    #result[taulist[ind]] = sum[ind]/cnt
    #P.append(abs(sum[ind])/cnt/pref*XSY/B/W*1.E-52*1.E12)   #1Jy=E-26W/m2/Hz
    P.append(summ[ind]/nT*1.E12)
print len(taulist), len(P)
kz = taulist*2*n.pi/Y
plotp.P_v_Eta(kz,P)


#Bootstrap resampling

B = 100
datab1 = data1

boot = []
for b in range(B):
    temps = []
    for i in range(len(data1[0])):    #for each channel
        temps.append(0.)
        for j in range(len(data1)):      #for each sample
            poin = random.choice(data1)[i]    #for each resample b
            temps[i] = temps[i] + n.conjugate(poin)*poin/len(data1)
    boot.append(temps)
boot = n.array(boot).transpose()
print boot.shape
bootmean,bootsig = [],[]
for ch in range(len(boot)):
    mean = n.sum(boot[ch])/B
    sig = n.sqrt(n.sum((boot[ch]-mean)**2)/B)
    bootmean.append(mean)
    bootsig.append(sig)
#p.hist(boot[5])
#p.show()

fig, ax = p.subplots()
ax.errorbar(n.arange(nchan), bootmean, yerr=bootsig, fmt='ok', ecolor='gray', alpha=0.5)
p.show()


