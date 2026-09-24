from django.contrib import admin
from .models import Profile,CategoryModel,ProductItem,ProductImage,Order,ContactUs
from django.utils.html import format_html

admin.site.register([Profile,CategoryModel,ProductItem,ProductImage,ContactUs])



@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = [
        'order_number', 
        'owner_display',
        'status_badge',
        'item_count',
        'total_price_display',
        'shipping_address_short',
        'created_at'
    ]
    
    list_filter = ['status', 'created_at', 'shipping_address']
    search_fields = ['order_number', 'owner__user__username', 'shipping_address']
    readonly_fields = [
        'order_number',
        'order_summary',
        'items_detailed_display', 
        'created_at',
        'item_count',
        'total_price'
    ]
    
    fieldsets = [
        ('Order Information', {
            'fields': [
                'order_number',
                'owner',
                'status',
                'shipping_address',
                'created_at'
            ]
        }),
        ('Order Summary', {
            'fields': [
                'order_summary',
                'item_count', 
                'total_price'
            ]
        }),
        ('Order Items', {
            'fields': ['items_detailed_display']
        }),
        ('Raw Data (Technical)', {
            'fields': ['items'],
            'classes': ['collapse']
        }),
    ]
    
    # List display methods
    def owner_display(self, obj):
        return obj.owner.user.username
    owner_display.short_description = 'Customer'
    
    def status_badge(self, obj):
        colors = {
            'pending': '#ff9800',
            'confirmed': '#2196f3', 
            'delivered': '#4caf50',
            'cancelled': '#f44336'
        }
        color = colors.get(obj.status, '#666')
        return format_html(
            '<span style="background: {}; color: white; padding: 4px 8px; border-radius: 12px; font-size: 12px;">{}</span>',
            color, obj.get_status_display()
        )
    status_badge.short_description = 'Status'
    
    def total_price_display(self, obj):
        return f"${obj.total_price}"
    total_price_display.short_description = 'Total'
    
    def shipping_address_short(self, obj):
        if len(obj.shipping_address) > 20:
            return f"{obj.shipping_address[:20]}..."
        return obj.shipping_address
    shipping_address_short.short_description = 'Shipping Address'
    
    # Detail view methods
    def order_summary(self, obj):
        items = self.get_formatted_items(obj)
        total_quantity = sum(item.get('quantity', 1) for item in items)
        
        html = f"""
        <div style="background: #f8f9fa; padding: 20px; border-radius: 10px; border-left: 4px solid #007cba;">
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px;">
                <div style="text-align: center;">
                    <div style="font-size: 24px; font-weight: bold; color: #007cba;">{obj.item_count or 0}</div>
                    <div style="color: #666; font-size: 14px;">Total Items</div>
                </div>
                <div style="text-align: center;">
                    <div style="font-size: 24px; font-weight: bold; color: #28a745;">{total_quantity}</div>
                    <div style="color: #666; font-size: 14px;">Total Quantity</div>
                </div>
                <div style="text-align: center;">
                    <div style="font-size: 24px; font-weight: bold; color: #dc3545;">${obj.total_price}</div>
                    <div style="color: #666; font-size: 14px;">Total Amount</div>
                </div>
                <div style="text-align: center;">
                    <div style="font-size: 24px; font-weight: bold; color: #6f42c1;">{obj.shipping_address}</div>
                    <div style="color: #666; font-size: 14px;">Delivery Location</div>
                </div>
            </div>
        </div>
        """
        return format_html(html)
    order_summary.short_description = 'Order Summary'
    
    def items_detailed_display(self, obj):
        items = self.get_formatted_items(obj)
        
        if not items:
            return format_html(
                '<div style="text-align: center; color: #666; padding: 40px; background: #f9f9f9; border-radius: 8px;">'
                'No items in this order'
                '</div>'
            )
        
        html = '<div style="display: grid; gap: 16px; max-width: 100%;">'
        
        for i, item in enumerate(items, 1):
            # Extract item data
            image_url = item.get('images', [{}])[0].get('image', '') if item.get('images') else ''
            category_name = item.get('category', {}).get('name', 'No Category')
            item_name = item.get('name', 'Unknown Item')
            location = item.get('location', 'Unknown')
            price = item.get('price', 0)
            quantity = item.get('quantity', 1)
            item_total = price * quantity
            description = item.get('description', 'No description available')
            
            html += f"""
            <div style="border: 1px solid #e1e5e9; border-radius: 12px; padding: 20px; background: white; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                <div style="display: flex; align-items: flex-start; gap: 20px;">

                    <div style="flex-shrink: 0;">
                        {f'<img src="{image_url}" style="width: 100px; height: 100px; object-fit: cover; border-radius: 8px; border: 1px solid #eee;" alt="{item_name}">' if image_url else '<div style="width: 100px; height: 100px; background: #f8f9fa; display: flex; align-items: center; justify-content: center; border-radius: 8px; color: #999; border: 1px dashed #ddd;"><span>No Image</span></div>'}
                    </div>
                    
                    <div style="flex-grow: 1; min-width: 0;">

                        <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 12px;">
                            <div>
                                <h3 style="margin: 0 0 5px 0; color: #2c3e50; font-size: 18px;">{item_name}</h3>
                                <div style="color: #7f8c8d; font-size: 14px;">
                                    <strong>Category:</strong> {category_name} | 
                                    <strong> Store Location:</strong> {location}
                                </div>
                            </div>
                            <span style="background: #3498db; color: white; padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: bold;">Item #{i}</span>
                        </div>
                        
                        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; margin-bottom: 12px; padding: 12px; background: #f8f9fa; border-radius: 6px;">
                            <div>
                                <strong style="color:black;">Unit Price:</strong><br>
                                <span style="color: #2c3e50;font-size:24px;">{price:.2f} ETB</span>
                            </div>
                            <div>
                                <strong style="color:black;">Quantity:</strong><br>
                                <span style="color: #2c3e50;font-size:24px;">{quantity}</span>
                            </div>
                            <div>
                                <strong style="color:black;">Item Total:</strong><br>
                                <span style="color: #27ae60;font-size:24px; font-weight: bold;">{item_total:.2f} ETB</span>
                            </div>
                        </div>
                        
                        <div style="color: #5d6d7e; font-size: 14px; line-height: 1.5;">
                            <strong>Description:</strong> {description[:120]}{'...' if len(description) > 120 else ''}
                        </div>
                    </div>
                </div>
            </div>
            """
        
        html += '</div>'
        return format_html(html)
    
    items_detailed_display.short_description = 'Order Items Details'
    
    # Helper method to get formatted items
    def get_formatted_items(self, obj):
        """Extract and format items data for display"""
        try:
            items_data = obj.items
            if isinstance(items_data, list):
                return items_data
            elif isinstance(items_data, dict):
                return [items_data]  # Single item as dict
            else:
                return []
        except (TypeError, AttributeError):
            return []