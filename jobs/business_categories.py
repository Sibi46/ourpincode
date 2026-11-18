"""Business categories shared by registration and business profile editing."""
BUSINESS_CATEGORIES = (
    'Ice Cream Shop', 'Grocery Store', 'Supermarket', 'Convenience Store', 'Department Store',
    'Bakery', 'Sweet Shop', 'Restaurant', 'Cafe', 'Tea Shop', 'Juice Shop', 'Fast Food Shop',
    'Food Truck', 'Catering Service', 'Vegetable Shop', 'Fruit Shop', 'Dairy Shop',
    'Meat Shop', 'Fish Shop', 'Spice Shop', 'Organic Store', 'Pet Shop',
    'Clothing Store', 'Textile Shop', 'Tailoring Shop', 'Boutique', 'Footwear Shop',
    'Jewellery Shop', 'Watch Shop', 'Bags & Accessories Shop', 'Cosmetics Store',
    'Beauty Parlour', 'Hair Salon', 'Barber Shop', 'Spa', 'Gym & Fitness Centre',
    'Pharmacy', 'Clinic', 'Hospital', 'Dental Clinic', 'Optical Shop', 'Diagnostic Centre',
    'Mobile Phone Shop', 'Mobile Repair Shop', 'Electronics Store', 'Electrical Shop',
    'Computer Shop', 'Computer Repair Service', 'Home Appliance Store',
    'Hardware Store', 'Paint Shop', 'Plumbing Supplies', 'Building Materials Store',
    'Furniture Store', 'Home Decor Store', 'Kitchenware Shop', 'Gift Shop',
    'Stationery Shop', 'Book Shop', 'Toy Shop', 'Sports Shop', 'Flower Shop',
    'Printing Service', 'Photo Studio', 'Laundry & Dry Cleaning', 'Cleaning Service',
    'Automobile Dealer', 'Two Wheeler Dealer', 'Vehicle Repair Workshop',
    'Car Wash', 'Auto Spare Parts Shop', 'Tyre Shop', 'Petrol Station',
    'Travel Agency', 'Taxi Service', 'Courier Service', 'Transport Service',
    'Hotel', 'Lodge', 'Event Management', 'Wedding Services', 'Real Estate Agency',
    'Construction Service', 'Electrical Service', 'Plumbing Service', 'Carpentry Service',
    'School', 'College', 'Tuition Centre', 'Training Institute', 'Daycare',
    'IT Services', 'Software Company', 'Digital Marketing Agency', 'Accounting Service',
    'Insurance Agency', 'Financial Services', 'Legal Services', 'Consultancy',
    'Farm', 'Nursery & Garden Store', 'Agricultural Supplies', 'Factory',
    'Manufacturing Unit', 'NGO', 'Other',
)


def business_category_names(current=''):
    from .models import Industry
    legacy = ['Food & Beverage', 'Healthcare', 'Education', 'Technology', 'Retail',
              'Manufacturing', 'Construction', 'Agriculture', 'Transport & Logistics',
              'Hospitality', 'Finance', 'Professional Services', 'Groceries', 'Software',
              'Automotive', 'Beauty & Wellness', 'Real Estate', 'Textiles']
    active = [name for name in Industry.objects.filter(is_active=True).values_list('name', flat=True)
              if any(char.isalpha() for char in name)]
    names = set(BUSINESS_CATEGORIES) | set(legacy) | set(active)
    if current:
        names.add(current)
    return sorted(names - {'Other'}, key=str.casefold) + ['Other']
