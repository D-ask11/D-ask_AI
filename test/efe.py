def a():
    return 1
def b(e = a()):
    print(e)

b()