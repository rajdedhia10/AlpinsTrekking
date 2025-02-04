from django.shortcuts import render, redirect, get_object_or_404
from django.views import View
from django.urls import reverse
from django.http import HttpResponseRedirect
from django.contrib.auth import authenticate, login, logout
from .forms import UserLoginForm, PaymentForm
from .models import Customer, Hike, Guide, EnrolledHikers, NewsLetter, Contact
from django.contrib.auth.hashers import make_password
from django.contrib.auth.decorators import login_required
from django.views.decorators.debug import sensitive_variables
from django.conf import settings
from django.db.models import F
from django.contrib import messages
from django.contrib.auth.models import User
from .helper import send_forget_password_mail, email
from moneyed import Money
from google_currency import convert
import json
import uuid



# Create your views here.
def base(request):
    return render(request, 'base.html')


def index(request):
    list(messages.get_messages(request))
    if request.method == 'POST':
        if NewsLetter.objects.filter(email=request.POST.get("email")):
            messages.error(request, 'You are already registered with us!')
            return HttpResponseRedirect(reverse('main:index'))
        else:
            newsLetter = NewsLetter()
            newsLetter.name = request.POST.get("name")
            newsLetter.email = request.POST.get("email")
            newsLetter.save()
            messages.success(request, 'You are successfully registered with us!')
            return HttpResponseRedirect(reverse("main:index"))        
    return render(request, 'index.html', {"treks": Hike.objects.all().order_by('-id')[:5]})


def singleTrek(request, id):
    trek = get_object_or_404(Hike, pk=id)
    user = get_object_or_404(Guide, pk=trek.user_id)
    if EnrolledHikers.objects.filter(user=request.user.pk, hike = id):
        trek.booked = True
    print("User id", user)
    if trek is None or user is None:
        return redirect('/treks')
    return render(request, 'treks-single.html', {"trek": trek, "user": user})


@login_required(login_url='main:login')
def treks(request):
    enrolledHikers = EnrolledHikers.objects.filter(user=request.user.pk).values_list('hike')
    if request.method == "GET":
        search_text = request.GET.get('search')
        # print(search_text)
        if search_text is not None:
            occupied_treks = Hike.objects.filter(available_capcity__gte=F('group_size')).exclude(pk__in=enrolledHikers).filter(mountain__contains=search_text)

            available_treks = Hike.objects.filter(group_size__gt=F('available_capcity')).exclude(pk__in=enrolledHikers).filter(mountain__contains=search_text)

        else:
            # enrolledHikers brings list of treks which user has enrolled into

            # occupied_treks searches for all the treks which are already full and removes treks which user has already enrolled to
            occupied_treks = Hike.objects.filter(available_capcity__gte = F('group_size')).exclude(pk__in=enrolledHikers)

            # available_treks first filters which treks are available and excludes all the treks which user is already a part of
            available_treks = Hike.objects.filter(group_size__gt = F('available_capcity')).exclude(pk__in=enrolledHikers).order_by('cost')
    # print(available_treks)
    return render(request, 'treks.html', {"treks": available_treks, "occupied_treks": occupied_treks})


@login_required(login_url='main:login')
def myBooking(request):

    # enrolledHikers brings list of treks which user has enrolled into
    enrolledHikers = EnrolledHikers.objects.filter(user = request.user.pk).values_list('hike')
    if request.method == "GET":
        search_text = request.GET.get('search')
        # print(search_text)
        if search_text is not None:
            booked_treks = Hike.objects.filter(pk__in=enrolledHikers).filter(mountain__contains=search_text)
        else:
    # booked_treks searches all the treks which logged in user is enrolled to
            booked_treks = Hike.objects.filter(pk__in = enrolledHikers)

    return render(request, 'booking.html' ,{"booked_treks": booked_treks})


@login_required(login_url='main:login')
def logout_view(request):
    logout(request)
    return redirect('/')


@login_required(login_url='main:login')
def booking(request, id):
    hike = Hike.objects.get(pk=id)
    enrolledHikers = EnrolledHikers.objects.create(hike=hike, user=Customer.objects.get(pk=request.user.pk))
    hike.available_capcity += 1
    hike.save()
    if hasattr(settings, 'EMAIL_HOST_USER') and hasattr(settings, 'EMAIL_HOST_PASSWORD'):
        email(request, enrolledHikers.pk, False)
    msg = "Your booking has been confirmed. Thank you for choosing our service."
    msg2 = "An email containing the details of your booking has been sent to you."
    return render(request, "booking_confirm.html", {'flag': True, 'msg': msg, 'msg2': msg2})


class Login(View):
    form = UserLoginForm
    def get(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return render(request, 'login.html', {"form": self.form})
        else:
            return redirect('/')
    
    def post(self, request, *args, **kwargs):
        email = request.POST['email']
        password = request.POST['password']
        user = authenticate(username=email, password=password)
        if user is not None:
            login(request, user)
            # Redirect to a success page.
            return redirect(request.META.get('HTTP_REFERER', '/'))
        else:
            # Return an 'invalid login' error message.
            return render(request, 'login.html', {"form": self.form, "error" : 'Invalid username or password.'})


class Signup(View):
    # form = SignupForm
    def get(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return render(request, 'registration.html')
        else:
            return redirect(request.META.get('HTTP_REFERER', '/'))
    
    def post(self, request, *args, **kwargs):
        user = Customer()
        user.username = request.POST.get("email")
        user.email = request.POST.get("email")
        user.phone = request.POST.get("phone")
        user.age = request.POST.get("age")
        user.first_name = request.POST.get("fname")
        user.last_name = request.POST.get("lname")
        user.password = make_password(request.POST.get("password"))
        user.save()
        return redirect('/', {"success": "User details stored successfully"})


def ChangePassword(request , token):
    context = {}
    try:
        cust_obj = Customer.objects.filter(forget_password_token = token).first()
        print("Customer Object in change password",cust_obj)
        context = {'user_id' : cust_obj.id}

        if request.method == 'POST':
            new_password = request.POST.get('new_password')
            confirm_password = request.POST.get('reconfirm_password')
            user_id = request.POST.get('user_id')
            print("User_id",user_id)

            if user_id is  None:
                messages.success(request, 'No user id found.')
                return redirect(f'/change-password/{token}/')


            if  new_password != confirm_password:
                messages.success(request, 'both should  be equal.')
                return redirect(f'/change-password/{token}/')

            user_obj = Customer.objects.get(id = user_id)
            print("user_obj in cp",user_obj)
            user_obj.set_password(new_password)
            user_obj.save()
            return redirect('/login')

    except Exception as e:
        print(e)
    return render(request , 'change-password.html' , context)


def ForgetPassword(request):
    try:
        if request.method == 'POST':
            email= request.POST.get('email')
            print("Email",email )
            print("Customer",Customer.objects.filter(email=email).first())
            if Customer.objects.filter(email=email).first() == None:
                messages.success(request, 'No user found with this email.')
                return redirect('/forget-password')

            # user_obj = User.objects.get(email = email)
            token = str(uuid.uuid4())
            cust_obj= Customer.objects.get(email = email)
            cust_obj.forget_password_token = token
            cust_obj.save()
            print("Customer object",cust_obj)
            reset_url = request.build_absolute_uri('/change-password/')
            print("Only reset url ",reset_url)
            print(" reset url+token ",reset_url+token+"/")
            reset_url+=token+"/"
            send_forget_password_mail(cust_obj.email , reset_url)
            messages.success(request, 'An email is sent.')
            return redirect('/forget-password')

    except Exception as e:
        print(e)
    return render(request , 'forget-password.html')

def teams(request):
    return render(request, "team.html", {"team": Guide.objects.all()})


@login_required(login_url='main:login')
def payment(request, id):
    if request.method == 'POST':
        form = PaymentForm(request.POST)
        if form.is_valid():
            trek = get_object_or_404(Hike, pk=id)
            user = get_object_or_404(Guide, pk=trek.user_id)
            price_today = json.loads(convert('cad', form.cleaned_data['currency'], trek.cost))
            sale_price_today = float(price_today['amount'])
            tax = float("{:.2f}".format(round(sale_price_today) * .13))
            total_price = tax + sale_price_today
            return render(request, "booking_confirm.html",
                          {"trek": trek, 'user': user, 'price': round(sale_price_today),
                           'tax': round(tax), 'total_price': round(total_price),
                           'cur': form.cleaned_data['currency']})

        else:
            return redirect(request.META.get('HTTP_REFERER', '/'))

    else:
        try:
            hikeCheck = EnrolledHikers.objects.get(user=request.user.pk, hike=id)
        except EnrolledHikers.DoesNotExist:
            hikeCheck = None
        if hikeCheck is not None:
            messages.error(request, "Sorry you've already enrolled for this trek")
            return redirect(request.META.get('HTTP_REFERER', '/'))
        hike = Hike.objects.get(pk=id)
        if hike is None:
            return redirect(request.META.get('HTTP_REFERER', '/'), {"error": "Sorry, no such trek exists"})
        if hike.available_capcity >= hike.group_size:
            return redirect(request.META.get('HTTP_REFERER', '/'),
                            {"error": "Sorry, you're late group capacity is full"})
        form = PaymentForm
        trek = get_object_or_404(Hike, pk=id)
        return render(request, "payment.html", {"trek_id": id, 'form': form, 'trek_cost': trek.cost, 'convert': convert})


@login_required(login_url='main:login')
def profile(request):
    user = Customer.objects.get(pk=request.user.id)
    if request.method == "GET":
        return render(request, "profile.html", {"profile": user})
    elif request.method == "POST":
        user.phone = request.POST.get("phone")
        user.age = request.POST.get("age")
        user.first_name = request.POST.get("fname")
        user.last_name = request.POST.get("lname")
        user.save()
        return render(request, "profile.html", {"profile": user, "success":"Your details are updated successfully"})

def contact(request):
    list(messages.get_messages(request))
    if request.method == "POST":
        contact = Contact()
        contact.name = request.POST.get("name")
        contact.email = request.POST.get("email")
        contact.description = request.POST.get("message")
        contact.save()
        messages.success(request, 'Congratulations. Your message has been sent successfully')
        return HttpResponseRedirect(reverse('main:contact'))
    return render(request, "contact.html")

@login_required(login_url='main:login')
def cancelBooking(request, id):
    try:
        hike = Hike.objects.get(pk = id)
    except Hike.DoesNotExist:
        messages.error(request, 'Sorry, no such trek Exists!')
        return redirect(request.META.get('HTTP_REFERER', '/'))
    try:
        enrolledHikers = EnrolledHikers.objects.get(user=request.user.pk, hike = id)
    except:
        messages.error(request, 'Sorry, you are not enrolled to this hike!')
        return redirect(request.META.get('HTTP_REFERER', '/'))
    email(request, enrolledHikers.pk, True)    
    enrolledHikers.delete()
    hike.available_capcity -= 1
    hike.save()
    return render(request, "cancel.html")