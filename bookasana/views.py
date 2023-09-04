from django.shortcuts import render


def faq(request):
    return render(request, 'faq.html')


def handler404(request):
    return render(request, '404.html', status=404)


def handler500(request):
    return render(request, '500.html', status=500)


def index(request):
    return render(request, 'index.html')


def robots(request):
    return render(request, 'robots.txt')


def terms_of_service(request):
    return render(request, 'terms_of_service.html')


def privacy_policy(request):
    return render(request, 'privacy_policy.html')

